export function formatMoney(currency, amount) {
  const numericAmount = Number(amount || 0);
  return `${currency || ''} ${new Intl.NumberFormat('en-GB').format(numericAmount)}`.trim();
}

export function formatDate(date) {
  return date || '-';
}
