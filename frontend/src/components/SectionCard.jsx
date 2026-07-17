export default function SectionCard({ title, children, action, className = '' }) {
  return (
    <section className={`overflow-hidden rounded-lg bg-white shadow-enterprise ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-3 bg-[#003A8C] px-5 py-3 text-white">
          <h2 className="text-sm font-bold uppercase tracking-wide">{title}</h2>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}
