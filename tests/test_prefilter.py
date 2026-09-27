import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
from leadpilot import db, pipeline, rules, excel
from cleanup_unqualified import cleanup


class PrefilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=db.DB_PATH
        db.DB_PATH=Path(self.tmp.name)/'test.sqlite3'
        db.init()
        self.cfg=rules.config({'min_reviews':10,'active_days':60})
        self.rid=pipeline.create(self.cfg)
        self.good=pipeline.fixtures(self.cfg)[0]

    def tearDown(self):
        db.DB_PATH=self.old
        self.tmp.cleanup()

    def test_invalid_candidates_never_saved_or_exported(self):
        bad=[]
        changes=[{'website':'https://business.example'}, {'address':'  '},
                 {'title':'null'}, {'totalScore':1.9}, {'reviewsCount':9},
                 {'reviews':[]}, {'permanentlyClosed':True},
                 {'totalScore':'NaN'}, {'reviewsCount':None},
                 {'reviews':[{'publishedAtDate':'2020-01-01T00:00:00Z'}]}]
        for n, change in enumerate(changes):
            row={**copy.deepcopy(self.good),**change,'placeId':f'bad-{n}'}
            bad.append(row)
        pipeline.ingest(self.rid,bad+[self.good,self.good])
        self.assertEqual(db.one('SELECT count(*) n FROM leads')['n'],1)
        self.assertEqual(db.one('SELECT count(*) n FROM businesses')['n'],1)
        wb=load_workbook(io.BytesIO(excel.workbook(self.rid)))
        self.assertEqual(wb['Initial'].max_row,2)

    def test_empty_result_finishes_scrape_stage(self):
        pipeline.ingest(self.rid,[{**self.good,'website':'https://x.example'}])
        db.execute("UPDATE runs SET stage='initial' WHERE id=?",(self.rid,))
        pipeline.process(db.one('SELECT * FROM runs WHERE id=?',(self.rid,)))
        self.assertEqual(db.one('SELECT status FROM runs')['status'],'awaiting_research')

    def test_cleanup_backup_and_preserve_research(self):
        pipeline.ingest(self.rid,[self.good])
        with db.connect() as c:
            for n, research in enumerate(['{}','{"website_status":"exists"}']):
                bid=c.execute('INSERT INTO businesses(identity) VALUES(?)',(f'old-{n}',)).lastrowid
                c.execute("INSERT INTO leads(run_id,business_id,raw,status,research) VALUES(?,?,?,'rejected',?)",
                          (self.rid,bid,json.dumps({**self.good,'website':'https://x.example'}),research))
        self.assertEqual(cleanup(),1)
        self.assertEqual(db.one('SELECT count(*) n FROM leads')['n'],2)
        self.assertEqual(len(list((db.DB_PATH.parent/'backups').glob('*.sqlite3'))),1)
        self.assertEqual(cleanup(),0)


if __name__=='__main__': unittest.main()
