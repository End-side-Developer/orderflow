You are an expert full-stack product architect and senior AI engineer.

I want to build an advanced “Court Judgment to Verified Action Plan” flow inside an order-flow-style app. The goal is to make the system efficient, token-saving, explainable, cached, and game-changing for government decision-making.

Build the app flow exactly around the following concept:

PROJECT NAME:
From Court Judgments to Verified Action Plans

MAIN OBJECTIVE:
Create an AI-assisted system that reads court judgment PDFs, extracts important legal and administrative information, generates a full judgment understanding, then generates an action plan only after user review, then allows human verification, and finally shows only approved records in a trusted dashboard.

The system must be designed in a step-by-step order flow, not as one single AI generation.

IMPORTANT PRINCIPLE:
AI should generate each part only once and cache the result. If the same PDF is opened again, the app should reuse cached data instead of calling AI again. This is very important to save tokens, reduce cost, and make the app faster.

==================================================
OVERALL FLOW
==================================================

The app should have these main pages/stages:

1. Intake / PDF Upload Page
2. PDF Processing and Page-Level Extraction Page
3. Full Judgment Summary Page
4. AI Action Plan Generation Page
5. Human Review and Verification Page
6. Trusted Dashboard Page

==================================================
1. INTAKE / PDF UPLOAD PAGE
==================================================

When the user uploads or opens a judgment PDF and clicks the “Intake” button, the system should start preprocessing the PDF.

The system should:

- Accept scanned or digital judgment PDFs.
- Generate a unique hash/fingerprint for the PDF.
- Check if this PDF was already processed before.
- If cached data exists, load the previous extraction and summary immediately.
- If no cached data exists, start page-by-page AI extraction.

The UI should show clear progress, for example:

“PDF received successfully.”
“Checking existing cache...”
“No previous processing found. Starting extraction.”
“Extracting page 1/16...”
“Extracting page 2/16...”
“Generating page summary...”

Do not generate the final action plan at this stage.

==================================================
2. PDF PROCESSING AND PAGE-LEVEL EXTRACTION PAGE
==================================================

After the Intake button is clicked, the system should process the PDF page by page.

The system should pre-calculate content for every page so the PDF viewer can show fast AI results later without repeating AI calls.

For each page, extract and store:

- Raw text or OCR text
- Page summary
- Important paragraphs
- Legal directions
- Dates
- Parties
- Entities
- Departments
- Places, if available
- Source paragraph references
- Confidence score
- Page number
- Bounding box or text highlight reference if possible

The system should support controlled parallel processing.

If feasible, the AI can process multiple pages at the same time, but the system must avoid overloading the AI API.

Use safe concurrency control:

- Start with low parallelism.
- Increase only if stable.
- If RPM or TPM limit is reached, reduce parallelism.
- If API fails because of rate limit, wait automatically and continue.
- Never restart the whole PDF processing if only one page fails.
- Retry only the failed page.

The UI should show progress like:

“Page 4/16 is extracting by AI...”
“Page 5/16 is extracting by AI...”
“RPM limit reached. Waiting 65 seconds before continuing...”
“Retrying page 7 extraction...”
“Extraction completed for 16/16 pages.”

Every page-level result must be cached.

The user should be able to open the PDF viewer and see:

- Original PDF page
- AI-generated page summary
- Highlighted source paragraphs
- Extracted entities
- Extracted dates
- Important directions found on that page

This page-level extraction should never be repeated for the same PDF unless the user manually chooses “Regenerate this page”.

==================================================
3. FULL JUDGMENT SUMMARY PAGE
==================================================

After all page-level extraction is completed, generate the full PDF/judgment summary.

This summary should be generated from cached page-level data, not by reading the whole PDF again from scratch.

The full judgment summary should include:

A. Basic Case Information

Extract and show:

- Case number
- Court name
- Case type
- Judgment/order date
- Petitioner name
- Respondent name
- Government department involved
- Judge name, if available
- Disposal status, if available
- Main subject of case

B. Detailed Judgment Overview

Create a simple and detailed overview of the entire judgment.

It should explain:

- What the case is about
- Who filed the case
- Against whom the case was filed
- What problem or dispute was raised
- What the court observed
- What final direction/order was given

C. Key Directives

Extract all important court directions.

For each directive, show:

- Direction text in simple English
- Source page number
- Source paragraph reference
- Confidence score
- Whether it is mandatory or advisory
- Whether it requires compliance

D. Important Dates and Timelines

Extract all relevant dates:

- Order date
- Compliance deadline
- Appeal limitation period, if mentioned
- Hearing dates, if important
- Submission/reporting deadlines
- Any timeline mentioned by court

If a deadline is inferred, clearly mark it as “AI inferred” and not as directly stated.

E. Entities Involved

Show all important entities:

- Petitioner
- Respondent
- Government departments
- Officers
- Courts
- Advocates, if useful
- Institutions
- Locations

Also include extra available information if the judgment provides it.

F. Responsible Department

Identify the likely responsible department or authority.

Show:

- Primary responsible department
- Supporting department
- Legal department role
- Petitioner
- Respondent
- Reason for assigning responsibility
- Source evidence from PDF

G. Paragraph-to-Paragraph Flow Graph

Create a detailed case flow graph.

The graph should explain the judgment flow in simple sequence, such as:

1. Case filed by petitioner
2. Petitioner raised grievance
3. Respondent/government gave argument
4. Court examined facts
5. Court referred to law/rules
6. Court gave final direction
7. Department must take action
8. Appeal/compliance decision is required

This should be generated as a visual flow if possible and also as text.

H. Map Flow

If the PDF contains more than 3 meaningful places and those places create a valid serious case journey, generate a map flow.

The map flow should show:

- Places involved
- Movement or jurisdiction connection
- Department or office location connection
- Case-related location flow

Only generate map flow if it is meaningful. Do not force it.

If map flow is not useful, show:

“Map flow not generated because no meaningful location-based case flow was found.”

The full judgment summary must be cached after generation.

Do not generate the Action Plan automatically on this page.

The user should first review the full judgment summary and then click:

“Generate Action Plan”

==================================================
4. AI ACTION PLAN GENERATION PAGE
==================================================

The action plan should be generated only after the user reviews the full judgment summary and clicks the “Generate Action Plan” button.

The action plan should be generated only once and cached.

The action plan should include:

A. Main Required Action

Clearly explain what needs to be done.

Example:

“The Education Department must issue the appointment order within 30 days.”

B. Compliance Requirement

Explain whether the department needs to comply with the judgment.

Show:

- Compliance required: Yes/No/Needs Review
- Reason
- Source paragraph
- Deadline
- Risk if delayed

C. Appeal Consideration

Explain whether the department may need to consider appeal.

Important:
AI must not make a final legal decision.
It should only say “Appeal review required” or “Legal department should examine appeal possibility.”

Show:

- Appeal review required: Yes/No/Needs Legal Review
- Reason
- Limitation period if mentioned
- Inferred limitation period only if legally configurable
- Source evidence

D. Key Timelines

Show all action-related deadlines.

For each timeline:

- Action
- Start date
- Deadline date
- Source
- Whether directly stated or inferred
- Confidence score

E. Responsible Department and Officer Role

Identify who should act.

Show:

- Primary department
- Supporting department
- Legal department
- Finance department, if payment related
- Administrative officer role
- Compliance officer role

F. Nature of Action Required

Classify the action type:

- Payment
- Appointment
- Document submission
- Compliance report
- Policy decision
- Reconsideration
- Hearing/review
- Appeal review
- Record update
- Other

G. Step-by-Step Action Plan

Generate a clear ordered plan:

Step 1: Legal department reviews judgment.
Step 2: Responsible department confirms facts.
Step 3: Department decides comply or appeal.
Step 4: If complying, assign responsible officer.
Step 5: Complete required action before deadline.
Step 6: Upload compliance proof.
Step 7: Mark status as completed after verification.

H. Risk and Priority

Show:

- Priority: High/Medium/Low
- Risk level: High/Medium/Low
- Reason for risk
- Deadline sensitivity
- Possible consequence of delay

I. Source Evidence

Every action item must have source support from the PDF.

Show:

- Page number
- Paragraph text
- Highlight reference
- Confidence score

If the AI cannot find proper evidence, mark that action as:

“Needs human review.”

==================================================
5. HUMAN REVIEW AND VERIFICATION PAGE
==================================================

After the AI Action Plan is generated, move to a human verification page.

This page is mandatory.

No AI-generated action plan should directly go to the dashboard without human approval.

The review page should show:

- Extracted case details
- Full judgment summary
- Key directives
- Action plan
- Important dates
- Responsible department
- Source highlights from PDF
- Confidence levels

For each action item, the human reviewer should have options:

- Approve
- Edit
- Reject
- Regenerate this item only

Important:
If the user chooses regeneration, regenerate only that specific part. Do not regenerate the full PDF extraction or full action plan.

Examples:

- Regenerate only one action item
- Regenerate only one timeline
- Regenerate only one responsible department suggestion
- Regenerate only one page extraction
- Regenerate only one directive

The app must maintain version history:

- Original AI output
- Edited human output
- Reviewer name
- Review timestamp
- Approval status
- Rejection reason, if rejected

Only approved or edited-and-approved records should move forward.

Rejected records should not appear in the dashboard.

==================================================
6. TRUSTED DASHBOARD PAGE
==================================================

The dashboard should show only human-approved action plans.

It must not show unverified AI output.

The dashboard should include:

A. Department-Wise View

Group action plans by department.

Example:

- Education Department
- Finance Department
- Revenue Department
- Legal Department

B. Key Actions Required

Show clear action items.

Example:

“Release payment”
“Issue appointment order”
“Submit compliance report”
“Review appeal possibility”

C. Important Dates

Show:

- Judgment date
- Compliance deadline
- Appeal review deadline
- Internal review deadline
- Status update date

D. Status

Show action status:

- Pending
- In Review
- Approved
- In Progress
- Completed
- Delayed
- Rejected

E. Filters

Add filters:

- Department
- Priority
- Deadline
- Status
- Case type
- Court
- Responsible authority

F. Decision-Maker View

Dashboard should be clean and reliable.

It should help senior officers quickly understand:

- What action is required
- Who is responsible
- What is the deadline
- What is pending
- What is delayed
- What is already completed

==================================================
CACHING AND TOKEN-SAVING REQUIREMENTS
==================================================

Use caching at every important level.

Cache keys should be based on:

- PDF hash
- Page number
- Prompt version
- Model version
- Extraction type
- User/manual regeneration flag

Cache these separately:

1. Page-level text extraction
2. Page-level summaries
3. Page-level entities
4. Page-level dates
5. Page-level directives
6. Full judgment summary
7. Flow graph
8. Map flow
9. Action plan
10. Human review result

Do not call AI again if cached result exists.

Only call AI again when:

- Cache is missing
- User clicks regenerate
- Prompt version changed
- Model version changed
- Previous generation failed
- Human reviewer requests improvement

==================================================
RATE LIMIT AND FAILURE HANDLING
==================================================

The app must gracefully handle AI API limits.

Handle:

- RPM limit
- TPM limit
- Timeout
- Network error
- Partial extraction failure
- OCR failure
- Invalid AI response
- JSON parsing error

When rate limit happens:

- Show reason clearly
- Wait automatically
- Add buffer time
- Reduce parallelism
- Continue from last successful page

Example UI messages:

“RPM limit reached. Waiting 60 seconds plus buffer time.”
“TPM limit reached. Reducing parallel page processing.”
“Page 6 failed. Retrying only page 6.”
“Extraction paused temporarily due to AI limit.”
“Processing will continue from page 7.”

Never lose previous successful progress.

==================================================
AI OUTPUT FORMAT REQUIREMENTS
==================================================

All AI outputs must be structured JSON.

For page extraction, use this format:

{
  "page_number": 1,
  "page_summary": "",
  "important_paragraphs": [
    {
      "paragraph_text": "",
      "reason": "",
      "source_location": "",
      "confidence": 0.0
    }
  ],
  "entities": [],
  "dates": [],
  "directions": [],
  "departments": [],
  "places": [],
  "confidence": 0.0
}

For full judgment summary, use this format:

{
  "case_details": {
    "case_number": "",
    "court_name": "",
    "case_type": "",
    "order_date": "",
    "petitioner": "",
    "respondent": "",
    "judge_name": "",
    "department_involved": ""
  },
  "overview": "",
  "key_directives": [],
  "important_dates": [],
  "entities_involved": [],
  "responsible_departments": [],
  "paragraph_flow_graph": [],
  "map_flow": {
    "available": false,
    "reason": "",
    "places": [],
    "flow": []
  },
  "confidence": 0.0
}

For action plan, use this format:

{
  "main_required_action": "",
  "compliance_requirement": {
    "required": "",
    "reason": "",
    "deadline": "",
    "source": "",
    "confidence": 0.0
  },
  "appeal_consideration": {
    "required": "",
    "reason": "",
    "limitation_period": "",
    "source": "",
    "confidence": 0.0
  },
  "key_timelines": [],
  "responsible_departments": [],
  "nature_of_action": [],
  "step_by_step_plan": [],
  "risk_and_priority": {
    "priority": "",
    "risk_level": "",
    "reason": ""
  },
  "source_evidence": []
}

For human verification, use this format:

{
  "verification_status": "approved | edited | rejected | needs_regeneration",
  "reviewer_name": "",
  "reviewed_at": "",
  "approved_items": [],
  "edited_items": [],
  "rejected_items": [],
  "comments": ""
}

==================================================
SECURITY AND TRUST REQUIREMENTS
==================================================

This system is only a decision-support system.

It must not claim that AI is giving final legal advice.

Always show:

“AI-generated result. Human verification required.”

Before dashboard publishing, show:

“Only verified records are shown in the dashboard.”

Every AI claim must be connected with source evidence from the PDF.

Any low-confidence result should be marked as:

“Needs human review.”

==================================================
EXPECTED FINAL PRODUCT BEHAVIOR
==================================================

The final app should feel like this:

1. User uploads judgment PDF.
2. User clicks Intake.
3. App extracts page-by-page data and caches it.
4. User can view PDF with page summaries and highlights.
5. App generates full judgment summary.
6. User reviews the full summary.
7. User clicks Generate Action Plan.
8. App generates action plan once and caches it.
9. User reviews AI action plan with PDF source highlights.
10. User approves, edits, rejects, or regenerates only selected parts.
11. Only approved action plans move to dashboard.
12. Dashboard shows trusted department-wise action records.

==================================================
TECHNICAL EXPECTATION
==================================================

Design the system using a modular architecture.

Suggested modules:

- PDF Intake Module
- PDF Hashing Module
- OCR/Text Extraction Module
- Page-Level AI Extraction Module
- Cache Manager
- Rate Limit Manager
- Summary Generator
- Action Plan Generator
- Source Highlight Mapper
- Human Verification Module
- Dashboard Module
- Audit Log Module

The system should be scalable, explainable, and safe for government use.

Prioritize:

- Speed
- Caching
- Token saving
- Human verification
- Source evidence
- Clean dashboard
- Retry and recovery
- Modular code
- Simple user experience

Build this as a production-ready flow.