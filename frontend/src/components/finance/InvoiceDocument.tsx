'use client';

import { invoiceItems, salesTerms } from '@/lib/invoice-content';
import { Category, Customer, Invoice, Preview, Receipt, currency, groupEntries, statusLabel, vehicleName } from '@/lib/finance';

export function PaymentStamp({ status }: { status: string }) {
  return <div className={`payment-stamp stamp-${status}`} aria-label={`Payment status: ${statusLabel(status)}`}>{statusLabel(status)}</div>;
}
function BillingContact({ customer, status }: { customer: Customer; status: string }) {
  return <div className="invoice-bill-to flex items-start gap-7">
    <div className="min-w-0 text-sm leading-relaxed"><p className="text-xs uppercase tracking-widest text-slate-500">Bill to</p><h3 className="text-lg font-semibold text-slate-900">{customer.name}</h3><p>{customer.email}</p><p>{customer.phone}</p><p className="whitespace-pre-line">{customer.formatted_address}</p></div>
    <PaymentStamp status={status} />
  </div>;
}
export function InvoicePaper({ invoice }: { invoice: Preview & Partial<Invoice> }) {
  return <article className="invoice-paper space-y-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-9 text-slate-800">
    <div className="flex flex-wrap justify-between gap-4 border-b border-slate-200 pb-5"><div><h2 className="text-2xl font-bold tracking-tight text-blue-900">RoieTrackers</h2><p className="text-sm text-slate-500">Customer invoice · NGN</p></div><div><h3 className="text-lg font-semibold">{invoice.number || 'DRAFT INVOICE'}</h3><p className="text-sm capitalize">{invoice.status || 'Draft for review'}</p>{invoice.issued_at && <p className="text-sm">Issued: {new Date(invoice.issued_at).toLocaleDateString()}</p>}{invoice.due_date && <p className="text-sm">Due: {invoice.due_date}</p>}</div></div>
    <BillingContact customer={invoice.customer} status={invoice.status === 'void' ? 'void' : invoice.payment_status || 'unpaid'} />
    <div className="space-y-6">{(['installation', 'renewal', 'maintenance', 'special'] as Category[]).map(category => {
      const groups = groupEntries(invoice.entries).filter(group => group.category === category);
      if (!groups.length) return null;
      const title = category === 'installation' ? 'Installations' : category === 'renewal' ? 'Renewal' : category === 'maintenance' ? 'Maintenance' : 'Special Service';
      return <section className="invoice-task space-y-4" key={category}><h4 className="invoice-task-heading rounded-lg bg-slate-100 p-3 font-semibold">{title}</h4>
        {groups.map((group, index) => <div className="invoice-rate-group" key={index}>
          {group.activity && <p className="mb-2 text-sm text-slate-600">{group.activity}</p>}
          {group.task_notes && <p className="task-explanation mb-3 whitespace-pre-wrap text-sm text-slate-600">{group.task_notes}</p>}
          {groups.length > 1 && <p className="mb-2 text-xs text-slate-500">{currency(group.unit_total_minor)} per vehicle</p>}
          <table className="invoice-breakdown w-full text-sm"><thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="p-2">Item</th><th className="p-2 text-right">Qty</th><th className="p-2 text-right">Price</th><th className="p-2 text-right">Amount</th></tr></thead><tbody>{invoiceItems(group).map((part, partIndex) => <tr key={partIndex} className="border-b border-slate-100"><td className="p-2"><strong className="font-medium">{part.label}</strong>{part.description && <span className="mt-1 block text-xs leading-relaxed text-slate-500">{part.description}</span>}</td><td className="p-2 text-right tabular-nums">{group.entries.length}</td><td className="p-2 text-right tabular-nums">{currency(part.amount_minor)}</td><td className="p-2 text-right tabular-nums">{currency(part.amount_minor * group.entries.length)}</td></tr>)}</tbody></table>
          {category !== 'special' && <div className="invoice-vehicles mt-3 text-sm leading-relaxed"><strong>Vehicles for {title.toLowerCase()} ({group.entries.length}): </strong>{group.entries.map((entry, vehicleIndex) => <span key={entry.id || vehicleIndex}>{vehicleIndex > 0 ? ', ' : ''}<span className="invoice-vehicle-name">{vehicleName(entry)}{!entry.device ? ' (awaiting installation)' : ''}</span></span>)}</div>}
          {groups.length > 1 && <p className="mt-2 text-right text-sm font-medium">Group total: {currency(group.total_minor)}</p>}
        </div>)}
        <p className="invoice-task-subtotal flex justify-between gap-3 border-t border-slate-200 pt-3 font-semibold"><span>{title} subtotal</span><span>{currency(groups.reduce((sum, group) => sum + group.total_minor, 0))}</span></p>
      </section>;
    })}</div>
    <div className="invoice-totals ml-auto max-w-sm space-y-2 border-t border-slate-200 pt-4 text-sm">
      <p className="flex justify-between gap-3"><span>Subtotal</span><span>{currency(invoice.subtotal_minor ?? invoice.total_minor)}</span></p>
      {!!invoice.discount_minor && <p className="flex justify-between gap-3 text-blue-800"><span>Discount{invoice.discount?.type === 'percent' ? ` (${invoice.discount.value}%)` : ''}</span><span>−{currency(invoice.discount_minor)}</span></p>}
      <p className="flex justify-between gap-3 text-xl font-bold text-slate-900"><span>Total</span><span>{currency(invoice.total_minor)}</span></p>
      {invoice.paid_minor !== undefined && <><p className="flex justify-between gap-3"><span>Paid</span><span>{currency(invoice.paid_minor)}</span></p><p className="flex justify-between gap-3 font-semibold"><span>Balance</span><span>{currency(invoice.balance_minor || 0)}</span></p></>}
    </div>
    {invoice.notes && <p className="whitespace-pre-wrap border-t border-slate-200 pt-4 text-sm">{invoice.notes}</p>}
    <section className="invoice-payment-details rounded-xl bg-slate-50 p-4 text-sm"><h4 className="mb-2 font-semibold">Payment details</h4><p>Bank Name: <strong>GTBank</strong></p><p>Account Number: <strong className="tracking-wide">0421439134</strong></p><p>Account Name: <strong>Roie Technologies Ltd</strong></p></section>
    {invoice.entries.some(entry => entry.category === 'installation') && <section className="invoice-sales-terms border-t border-slate-200 pt-4"><h4 className="mb-3 font-semibold">Sales Terms</h4><ol className="list-decimal space-y-1 pl-5 text-xs leading-relaxed text-slate-600">{salesTerms.map(term => <li key={term}>{term}</li>)}</ol><div className="mt-6 flex flex-wrap gap-8 text-xs text-slate-500"><p>Customer signature: ________________________</p><p>Date: __________________</p></div></section>}
    {invoice.status === 'void' ? <p className="text-sm text-red-700">VOID — this invoice is cancelled.</p> : invoice.status !== 'issued' && <p className="text-xs text-slate-500">Draft for review. This is not an issued invoice.</p>}
  </article>;
}
export function ReceiptPaper({ receipt }: { receipt: Receipt }) {
  return <article className="invoice-paper receipt-paper space-y-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-9 text-slate-800">
    <div className="flex flex-wrap justify-between gap-4 border-b border-slate-200 pb-5"><div><h2 className="text-2xl font-bold text-blue-900">RoieTrackers</h2><p className="text-sm text-slate-500">{receipt.kind === 'combined' ? 'Combined payment receipt' : 'Payment receipt'} · NGN</p></div><div><h3 className="font-semibold">{receipt.number}</h3><p className="text-sm">Invoice: {receipt.invoice_number}</p><p className="text-sm">Date: {new Date(receipt.as_of).toLocaleDateString()}</p></div></div>
    <BillingContact customer={receipt.customer} status={receipt.balance_minor === 0 ? 'paid' : 'partial'} />
    <table className="invoice-breakdown w-full text-sm"><thead><tr className="border-b text-left text-slate-500"><th className="p-2">Date / reference</th><th className="p-2">Method</th><th className="p-2 text-right">Received</th></tr></thead><tbody>{receipt.payments.map(payment => <tr key={payment.id} className="border-b border-slate-100"><td className="p-2">{payment.paid_on}<span className="block text-slate-500">{payment.reference}</span></td><td className="p-2 capitalize">{payment.method.replaceAll('_', ' ')}</td><td className="p-2 text-right">{currency(payment.amount_minor)}</td></tr>)}</tbody></table>
    <div className="invoice-totals ml-auto max-w-sm space-y-3 text-sm"><p className="flex justify-between gap-3 text-xl font-bold"><span>Received</span><span>{currency(receipt.received_minor)}</span></p><p className="flex justify-between gap-3"><span>Invoice total</span><span>{currency(receipt.invoice_total_minor)}</span></p><p className="flex justify-between gap-3"><span>Total paid as of this receipt</span><span>{currency(receipt.cumulative_paid_minor)}</span></p><p className="flex justify-between gap-3 font-semibold"><span>Remaining balance</span><span>{currency(receipt.balance_minor)}</span></p></div>
    <p className="text-sm text-slate-500">Thank you for choosing RoieTrackers.</p>
  </article>;
}
