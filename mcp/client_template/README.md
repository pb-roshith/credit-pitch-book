# Intel MCP

Local MCP service for the credit intelligence Excel tables.

## Tables

- `credit_balance_sheet`
- `credit_cashflow_statement`
- `credit_income_statement`
- `credit_bank_statements`
- `credit_net_worth_statement`
- `credit_projected_financials`
- `section2_customer_information`
- `section2_ownership_structure`

## Mistral PDF MCP Tools

The local MCP server exposes 17 per-PDF tools for the configured Mistral library:

```text
get_property_documents_content
get_pan_card_content
get_purpose_of_loan_content
get_kyc_identity_proofs_content
get_litigation_details_content
get_moa_aoa_content
get_income_tax_returns_3_years_content
get_kyc_income_tax_returns_content
get_kyc_credit_reports_content
get_key_customers_suppliers_content
get_gst_registration_content
get_declarations_content
get_gst_returns_content
get_existing_loan_details_content
get_company_profile_content
get_certificate_of_incorporation_content
get_asset_details_content
```

## Setup

```bash
cd intel_mcp
python server.py
```

The MCP server runs on:

```text
http://127.0.0.1:8010/mcp
```
