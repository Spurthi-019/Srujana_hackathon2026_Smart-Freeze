/**
 * Utility functions for money and number formatting in Smart Freeze.
 * Uses Rs Lakh / Crore formatting with exact value on hover.
 */

export function formatMoney(val) {
  const num = Number(val) || 0;
  const abs = Math.abs(num);

  if (abs >= 10000000) {
    return `₹${(num / 10000000).toFixed(2)} Cr`;
  }
  if (abs >= 100000) {
    return `₹${(num / 100000).toFixed(2)} L`;
  }
  return `₹${Math.round(num).toLocaleString('en-IN')}`;
}

export function formatMoneyExact(val) {
  const num = Number(val) || 0;
  return `₹${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatNumber(val, decimals = 2) {
  const num = Number(val) || 0;
  return num.toFixed(decimals);
}
