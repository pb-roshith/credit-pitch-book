export default function FormField({
  label,
  name,
  value,
  onChange,
  type = 'text',
  as = 'input',
  options = [],
  required = true,
}) {
  const common =
    'mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100';

  return (
    <label className="block">
      <span className="text-sm font-semibold text-slate-700">{label}</span>
      {as === 'select' ? (
        <select className={common} name={name} value={value} onChange={onChange} required={required}>
          <option value="">Select</option>
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : (
        <input className={common} name={name} type={type} value={value} onChange={onChange} required={required} />
      )}
    </label>
  );
}
