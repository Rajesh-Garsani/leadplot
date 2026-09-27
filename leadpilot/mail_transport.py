import smtplib, ssl
from email.message import EmailMessage
from . import vault

def smtp_connection():
    host=vault.get('SMTP_HOST','');port=int(vault.get('SMTP_PORT','587'))
    if not host:raise ValueError('Save your email connection first')
    smtp=None
    try:
        if vault.get('SMTP_SECURITY','starttls')=='ssl':smtp=smtplib.SMTP_SSL(host,port,timeout=25,context=ssl.create_default_context())
        else:
            smtp=smtplib.SMTP(host,port,timeout=25);smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
        if vault.get('SMTP_USER',''):smtp.login(vault.get('SMTP_USER'),vault.get('SMTP_PASSWORD',''))
        return smtp
    except Exception:
        if smtp:
            try:smtp.close()
            except Exception:pass
        raise

def message(sender,recipient,subject,body,message_id,parent='',refs=''):
    msg=EmailMessage();msg['From']=sender;msg['To']=recipient;msg['Subject']=subject;msg['Message-ID']=message_id
    if parent:msg['In-Reply-To']=parent
    if refs:msg['References']=refs
    msg.set_content(body);return msg
