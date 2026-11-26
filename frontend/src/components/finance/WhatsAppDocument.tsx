"use client";

import { useState } from 'react';
import { FiMessageCircle, FiDownload, FiShare2, FiCopy } from 'react-icons/fi';
import { Customer, Invoice, Receipt, downloadPdfFile, fetchDocumentPdf, financeApi, whatsappLink, whatsappMessage, whatsappPhone } from '@/lib/finance';
import { actionClass, secondaryClass } from './FinanceInputs';

export default function WhatsAppDocument({ invoice, receipt }: { invoice: Invoice; receipt?: Receipt }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [phone, setPhone] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [canShare, setCanShare] = useState(false);
  const message = whatsappMessage(invoice, receipt);
  if (invoice.status !== 'issued') return null;

  async function prepare() {
    if (open) { setOpen(false); return; }
    setOpen(true); setBusy(true); setError(''); setNotice(''); setFile(null); setPhone('');
    try {
      const [pdf, contact] = await Promise.all([
        fetchDocumentPdf(invoice, receipt),
        invoice.customer.traccar_user_id
          ? financeApi<{ customer: Customer }>(`customers/${invoice.customer.traccar_user_id}`)
          : Promise.resolve({ customer: invoice.customer }),
      ]);
      if (contact.customer.email.trim().toLowerCase() !== invoice.customer.email.trim().toLowerCase()) {
        throw new Error('The customer account email has changed. Verify the invoice contact before sharing.');
      }
      const normalized = whatsappPhone(contact.customer.phone || invoice.customer.phone || '');
      if (!normalized) throw new Error('Add a valid phone number to this customer profile, then try again.');
      setPhone(normalized); setFile(pdf);
      setCanShare(typeof navigator.share === 'function' && typeof navigator.canShare === 'function' && navigator.canShare({ files: [pdf] }));
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function sharePdf() {
    if (!file || busy) return;
    setBusy(true); setNotice(''); setError('');
    try {
      // The PDF is prepared before this click, preserving the user gesture
      // required by browsers for native file sharing.
      await navigator.share({ files: [file], title: receipt ? 'RoieTrackers receipt' : 'RoieTrackers invoice', text: message });
      setNotice('Shared with the selected app. Complete sending in WhatsApp.');
    } catch (err) {
      if ((err as Error).name !== 'AbortError') setError('File sharing is unavailable. Download the PDF and attach it in the customer chat.');
    } finally { setBusy(false); }
  }

  return <section aria-label="WhatsApp customer document" className="finance-no-print min-w-0 space-y-3">
    <div className="flex justify-end"><button type="button" className={`${secondaryClass} w-full justify-center sm:w-auto`} disabled={busy} aria-expanded={open} onClick={() => void prepare()}><FiMessageCircle aria-hidden="true" />{busy && !file ? 'Preparing PDF...' : 'Send to WhatsApp'}</button></div>
    {open && <div className="finance-card min-w-0 space-y-4">
      <div><h2 className="font-semibold">Send {receipt ? 'receipt' : 'invoice'} to WhatsApp</h2><p className="mt-1 break-words text-sm text-slate-600">{invoice.customer.name} &middot; {invoice.customer.email}</p>{phone && <p className="mt-1 text-sm font-semibold text-blue-900">+{phone}</p>}</div>
      {busy && !file && <p role="status" className="text-sm text-slate-500">Preparing the customer phone number and PDF...</p>}
      {error && <p role="alert" className="finance-error">{error}</p>}
      {file && <>
        <p className="text-sm text-slate-600">Open the customer chat with the message below. The PDF will download for you to attach before sending.</p>
        <textarea aria-label="WhatsApp message" readOnly value={message} rows={9} className="w-full resize-y rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm leading-relaxed" />
        <div className="grid gap-2 sm:flex sm:flex-wrap">
          <a className={`${actionClass} justify-center`} href={whatsappLink(phone, message)} target="_blank" rel="noopener noreferrer" onClick={() => { downloadPdfFile(file); setNotice('Attach the downloaded PDF in the customer chat, then send.'); }}><FiMessageCircle aria-hidden="true" />Open WhatsApp</a>
          {canShare && <button type="button" className={`${secondaryClass} justify-center`} disabled={busy} onClick={() => void sharePdf()}><FiShare2 aria-hidden="true" />Share PDF with app</button>}
          <button type="button" className={`${secondaryClass} justify-center`} onClick={() => downloadPdfFile(file)}><FiDownload aria-hidden="true" />Download PDF</button>
          <button type="button" className={`${secondaryClass} justify-center`} onClick={async () => { try { await navigator.clipboard.writeText(message); setNotice('Message copied.'); } catch { setNotice('Select and copy the message above.'); } }}><FiCopy aria-hidden="true" />Copy message</button>
        </div>
        {canShare && <p className="text-xs leading-relaxed text-slate-500">To attach directly, choose Share PDF with app, then WhatsApp Business and this customer in your device&apos;s share menu. The app and recipient cannot be preselected.</p>}
        <p className="text-xs leading-relaxed text-slate-500">WhatsApp must be installed or available on the web. WhatsApp checks whether this number has an account. You review and send the message there.</p>
      </>}
      {notice && <p role="status" className="rounded-lg bg-blue-50 p-3 text-sm text-blue-900">{notice}</p>}
    </div>}
  </section>;
}
