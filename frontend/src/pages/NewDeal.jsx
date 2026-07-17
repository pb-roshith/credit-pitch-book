import { ArrowLeft, Save, Send, X } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import FormField from '../components/FormField.jsx';
import SectionCard from '../components/SectionCard.jsx';
import { createDeal } from '../services/api.js';

const emptyDeal = {
  legalName: '',
  industry: '',
  geography: '',
  customerType: '',
  segment: '',
  kycStatus: '',
  facility: '',
  amount: '',
  pricing: '',
  collateralRequired: '',
  currency: '',
  tenure: '',
  repayment: '',
  targetCompletionDate: '',
};

export default function NewDeal() {
  const navigate = useNavigate();
  const [form, setForm] = useState(emptyDeal);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const updateField = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  };

  const submitDeal = async (status) => {
    setSubmitting(true);
    setError('');

    try {
      const deal = await createDeal({ ...form, status });
      navigate(`/deals/${deal.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      className="mx-auto max-w-6xl space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        submitDeal('In Review');
      }}
    >
      <Link to="/" className="inline-flex items-center gap-2 text-sm font-bold text-[#003A8C] hover:underline">
        <ArrowLeft size={17} />
        Back to Dashboard
      </Link>

      {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}

      <SectionCard title="Customer Details">
        <div className="grid gap-5 md:grid-cols-2">
          <div className="space-y-4">
            <FormField label="Legal Name" name="legalName" value={form.legalName} onChange={updateField} />
            <FormField label="Industry" name="industry" value={form.industry} onChange={updateField} />
            <FormField label="Geography" name="geography" value={form.geography} onChange={updateField} />
          </div>
          <div className="space-y-4">
            <FormField label="Customer Type" name="customerType" value={form.customerType} onChange={updateField} as="select" options={['New-to-bank', 'Existing client']} />
            <FormField label="Segment" name="segment" value={form.segment} onChange={updateField} as="select" options={['Mid Corporate', 'Large Corporate', 'Corporate Banking']} />
            <FormField label="KYC Status" name="kycStatus" value={form.kycStatus} onChange={updateField} as="select" options={['Verified', 'Refresh due', 'Pending']} />
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Facility Details">
        <div className="grid gap-5 md:grid-cols-2">
          <div className="space-y-4">
            <FormField label="Product / Facility Type" name="facility" value={form.facility} onChange={updateField} />
            <FormField label="Amount" name="amount" value={form.amount} onChange={updateField} type="number" />
            <FormField label="Pricing" name="pricing" value={form.pricing} onChange={updateField} />
            <FormField label="Collateral Required" name="collateralRequired" value={form.collateralRequired} onChange={updateField} as="select" options={['Yes', 'No']} />
          </div>
          <div className="space-y-4">
            <FormField label="Currency" name="currency" value={form.currency} onChange={updateField} as="select" options={['EUR', 'GBP', 'USD']} />
            <FormField label="Tenure" name="tenure" value={form.tenure} onChange={updateField} />
            <FormField label="Repayment" name="repayment" value={form.repayment} onChange={updateField} />
            <FormField label="Target Completion Date" name="targetCompletionDate" value={form.targetCompletionDate} onChange={updateField} type="date" />
          </div>
        </div>
      </SectionCard>

      <div className="flex flex-wrap justify-end gap-3 rounded-lg bg-white p-4 shadow-enterprise">
        <button
          type="button"
          disabled={submitting}
          onClick={() => submitDeal('Draft')}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-bold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save size={17} />
          Save Draft
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="inline-flex items-center gap-2 rounded-lg bg-[#003A8C] px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Send size={17} />
          {submitting ? 'Submitting...' : 'Submit for Review'}
        </button>
        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-bold text-slate-700"
        >
          <X size={17} />
          Cancel
        </Link>
      </div>
    </form>
  );
}
