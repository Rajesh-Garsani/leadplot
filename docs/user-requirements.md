## Project: Intelligent Business Lead Generation, Verification & Email Outreach System

Build a robust, automated lead-generation and outreach system using **n8n + Apify + Gemini/AI + Google Sheets**, with Python/JavaScript and other technologies where necessary.

### 1. Business Lead Scraping

The system should use an existing **Google Maps/Google Business scraping workflow in n8n + Apify**.

The user should be able to enter:

- Business niche/category
- Target location
- Number of leads to collect
- Business activity/active-days requirement
- Other optional filtering criteria
- Apify API key(s)

The Apify scraper should collect businesses matching the requested criteria and save the initial results to a **Google Sheet**.

The system should prioritize businesses that:

- Are currently active
- Match the requested niche
- Are located in the requested area
- Meet the minimum review requirement
- Meet the minimum rating requirement
- Have sufficient publicly available business information

---

### 2. Individual Business Research & Verification

After the initial scraping stage, the system should process **each business individually**.

For every business, send a research task to **Gemini AI/web-research system**.

The research agent should search multiple relevant sources and verify information rather than relying on a single search result.

Research should attempt to identify:

#### Business Information

- Business name
- Business category
- Address
- Phone number
- Email
- Google Maps URL
- Website status
- Social media profiles
- Business registration information, where publicly available

#### Decision Maker Information

Identify the most relevant publicly identifiable decision maker, such as:

- Owner
- Founder
- Manager
- Director
- Other appropriate business decision maker

Where publicly available, collect:

- Full name
- Position/designation
- Business-related email
- Business-related phone/mobile number
- Relevant professional/social profile
- Source URL(s) supporting the information

The system should distinguish between **verified information, probable information, and information that could not be found**.

Do not invent or guess contact information.

---

### 3. Website Verification

After completing the research, the system must determine whether the business currently has a website.

This should be a **verification step**, not simply a check of whether a website field was empty in the original Google Maps data.

The system should search for the business website using multiple relevant sources and determine:

- No website found
- Website exists
- Website appears outdated/broken, if this criterion is enabled
- Website status cannot be confidently determined

Only businesses that has no website should proceed to the final qualified-leads sheet.

---

### 4. Qualified Leads Sheet

Create a separate Google Sheet containing only businesses that pass all required verification and filtering criteria.

Recommended columns:

- Business Name
- Business Category
- Business Phone
- Business Email
- Business Address
- Google Maps URL
- Rating
- Review Count
- Website Status
- Decision Maker Name
- Decision Maker Position
- Decision Maker Email
- Decision Maker Phone
- Facebook URL
- Instagram URL
- LinkedIn URL
- Other Social Profile
- Business Registration Information
- Lead Status

The system should prevent duplicate businesses and preserve the source URLs used during verification.

---

### 5. Automated Email Personalization

After qualified leads have been created, the user should be able to provide an email template.

Example:

> Hi {{FirstName}},
>
> I came across {{BusinessName}} and noticed...
>
> [rest of email]

The system should automatically replace variables using the verified data from the Google Sheet.

Supported variables should include, where available:

- `{{FirstName}}`
- `{{FullName}}`
- `{{BusinessName}}`
- `{{BusinessCategory}}`
- `{{Location}}`
- `{{WebsiteStatus}}`
- `{{CustomResearchField}}`

The system should generate a personalized email for **each individual lead**.

If the decision maker's name cannot be reliably verified, the system should follow a configurable fallback rule rather than inventing a name.

---

### 6. Automated Email Sending

After personalization, the system should send emails individually using the verified email address.

The email-sending system should support:

- Configurable email provider
- Sending one email per lead
- Configurable delay between emails
- Daily sending limits
- Batch size
- Retry handling
- Failed-email logging
- Duplicate-send prevention
- Sent/failed/pending status
- Timestamp of each email
- Error message logging

The system should never send multiple emails to the same lead because of a workflow restart or duplicate record.

---

### 7. Intelligent Apify API-Key Management

The system should support **multiple Apify API keys**.

The user should be able to configure multiple keys, for example:

- Apify Key 1
- Apify Key 2
- Apify Key 3
- Apify Key 4

The system should automatically:

1. Use an available API key.
2. Monitor the Apify request/run response.
3. Detect quota, credit, rate-limit, or authorization problems.
4. Stop using a key when it becomes unavailable.
5. Automatically switch to the next available key.
6. Continue the workflow without losing processed data.
7. Track the status and usage of each key.
8. Retry failed operations when appropriate.
9. Avoid repeatedly using a key that has already failed.

API keys must be stored securely and never exposed in Google Sheets, logs, browser output, or generated emails.

---

### 8. User Configuration Interface

Create a simple configuration interface/dashboard if appropriate.

The user should be able to configure:

#### Scraping

- Niche
- Location
- Lead count
- Minimum rating
- Minimum reviews
- Active-business requirement
- Website requirement
- Other filters

#### Research

- AI provider/model
- Research prompt
- Required research fields
- Verification requirements

#### Outreach

- Email template
- Sender account
- Daily sending limit
- Delay between emails
- Batch size
- Follow-up settings, if enabled

#### API & Integrations

- Multiple Apify API keys
- Google Sheets credentials
- AI/Gemini credentials
- Email provider credentials
- Other required API credentials

---

### 9. Workflow Architecture

Design the system as a reliable multi-stage pipeline:

**User Input → Apify Scraping → Initial Google Sheet → Individual Business Research → Website Verification → Data Validation → Qualified Leads Sheet → Email Personalization → Email Sending → Tracking & Logging**

Each stage should have error handling and should be restartable without duplicating previously completed work.

The system should save intermediate results so that if one stage fails, it can resume from the last successful stage instead of starting the entire process again.

---

### 10. Data Quality & Verification

Data quality is more important than simply generating a large number of leads.

The system should:

- Avoid duplicate businesses.
- Validate phone numbers where possible.
- Validate email addresses where possible.
- Verify website status.
- Preserve source URLs.
- Avoid fabricated information.
- Clearly mark missing information.
- Distinguish verified data from unverified/probable data.
- Apply all user-defined qualification criteria before a lead reaches the outreach stage.

A lead should only proceed to email outreach when it satisfies the configured qualification rules.

---

### 11. Monitoring & Error Handling

Create a central workflow log containing:

- Workflow run ID
- Business name
- Processing stage
- Status
- Timestamp
- Error message
- Apify key used
- Research status
- Website verification status
- Email status
- Retry count

The system should handle:

- Apify failures
- API quota limits
- API rate limits
- Invalid API keys
- Gemini/AI failures
- Google Sheets errors
- Missing business information
- Missing decision-maker information
- Invalid email addresses
- Email-sending failures
- Duplicate records
- Workflow interruptions

---

### 12. Recommended Technology Stack

Use the following technologies where appropriate:

- **n8n** — workflow orchestration and automation
- **Apify** — Google Maps/business data extraction
- **Gemini or another suitable AI/web-research service** — individual business research and verification
- **Google Sheets** — lead database and workflow output
- **Python** — advanced processing, validation, and API management where useful
- **JavaScript/Node.js** — custom n8n logic and API integrations
- **HTML/CSS/JavaScript** — optional configuration dashboard
- **Database such as PostgreSQL/Supabase** — recommended if the system needs reliable large-scale tracking
- **Email API/provider** — automated personalized outreach

Use the simplest architecture that is reliable and maintainable. Do not add technologies unless they solve a specific requirement.

---

## Primary Objective

Build an **intelligent, reliable, and scalable lead-generation system** that does more than simply scrape businesses.

The complete system should:

**Find → Filter → Research → Verify → Qualify → Personalize → Send → Track**

The most important priority is **high-quality, verified, relevant leads rather than maximum scraping volume**.

The system should be designed so that the user can change the niche, location, lead count, qualification criteria, research prompt, email template, API keys, and outreach settings without rebuilding the workflow.

Provide:

1. Complete system architecture
2. n8n workflow design
3. Required n8n nodes and their configurations
4. Apify configuration
5. Gemini/AI research prompt
6. Google Sheets structure
7. Data-validation logic
8. Website-verification logic
9. Multi-Apify-key failover logic
10. Email personalization logic
11. Email-sending workflow
12. Error-handling and retry logic
13. Required credentials/API configuration
14. JavaScript/Python code where necessary
15. Step-by-step setup and deployment instructions

The final implementation should be **modular, fault-tolerant, secure, restartable, and easy to configure**, while minimizing unnecessary API usage and processing costs.