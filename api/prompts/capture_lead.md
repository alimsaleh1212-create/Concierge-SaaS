Based on the conversation so far, extract the visitor's contact details and call the `capture_lead` tool.

Extract the following fields if present in the conversation:
- visitor_name: the visitor's full name
- visitor_email: a valid email address
- visitor_phone: a phone number (optional)
- intent: a brief description of what the visitor is interested in

If any required field (visitor_name or visitor_email) is missing, ask the visitor for it before calling the tool.
Do not ask for information the visitor has already provided.
