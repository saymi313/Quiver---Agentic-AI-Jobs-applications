import { useRef, useState } from 'react'
import { api } from '../lib/api'
import { Sheet } from './apple'
import { Button, Field, Input, Note, Select, Textarea } from './ui'

/*
  An application made outside Jobenzy, entered by hand — or a whole spreadsheet
  of them imported at once.

  A tracker that only holds what the agent submitted is only half a tracker: the
  roles applied to before Jobenzy, or on a site it cannot reach, belong in the
  same pipeline. Both routes land in the same place as a submitted application,
  marked as the user's own rather than the applier's.
*/

const STAGES = ['applied', 'interviewing', 'offer', 'rejected', 'ghosted']

export default function AddApplication({ open, onClose, onAdded }) {
  const [form, setForm] = useState({
    title: '', company_name: '', url: '', tracker_status: 'applied', applied_on: '', notes: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [imported, setImported] = useState(null)
  const fileRef = useRef(null)

  const set = (patch) => setForm((f) => ({ ...f, ...patch }))

  const save = () => {
    setBusy(true)
    setError('')
    api
      .agentAddApplication(form)
      .then(() => {
        setForm({ title: '', company_name: '', url: '', tracker_status: 'applied',
                  applied_on: '', notes: '' })
        onAdded?.()
        onClose?.()
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const importCsv = (file) => {
    if (!file) return
    setBusy(true)
    setError('')
    setImported(null)
    api
      .agentImportApplications(file)
      .then((r) => {
        setImported(r)
        onAdded?.()
      })
      .catch((e) => setError(e.message))
      .finally(() => {
        setBusy(false)
        if (fileRef.current) fileRef.current.value = ''
      })
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Add an application"
      description="One you made outside Jobenzy, by hand or from a spreadsheet."
      footer={
        <div className="flex items-center gap-2">
          <Button variant="primary" busy={busy} disabled={!form.title.trim()} onClick={save}>
            Add to tracker
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {error ? (
          <Note tone="bad" title="Could not add it" onDismiss={() => setError('')}>
            {error}
          </Note>
        ) : null}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Role" className="col-span-2">
            <Input value={form.title} onChange={(e) => set({ title: e.target.value })}
                   placeholder="Software Engineer" />
          </Field>
          <Field label="Company">
            <Input value={form.company_name} onChange={(e) => set({ company_name: e.target.value })}
                   placeholder="Acme" />
          </Field>
          <Field label="Stage">
            <Select value={form.tracker_status}
                    onChange={(e) => set({ tracker_status: e.target.value })}>
              {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </Field>
          <Field label="Link">
            <Input value={form.url} onChange={(e) => set({ url: e.target.value })}
                   placeholder="https://…" />
          </Field>
          <Field label="Applied on">
            <Input type="date" value={form.applied_on}
                   onChange={(e) => set({ applied_on: e.target.value })} />
          </Field>
          <Field label="Notes" className="col-span-2">
            <Textarea rows={2} value={form.notes}
                      onChange={(e) => set({ notes: e.target.value })} />
          </Field>
        </div>

        {/* the bulk route, quieter, below the single-entry form */}
        <div className="rounded-md border border-line bg-raised p-3">
          <p className="text-tiny font-medium text-n-200">Import a spreadsheet</p>
          <p className="mt-0.5 text-micro leading-relaxed text-n-500">
            A CSV with columns like Company, Role, Status, Date, Link. Names are matched loosely,
            so an export from anywhere usually just works.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => importCsv(e.target.files?.[0])}
            className="mt-2 block w-full text-tiny text-n-400 file:mr-3 file:rounded-full
              file:border-0 file:bg-n-100 file:px-3 file:py-1 file:text-tiny file:font-medium
              file:text-n-950"
          />
          {imported ? (
            <p className="mt-2 text-micro text-ok-400">
              Imported {imported.added} application{imported.added === 1 ? '' : 's'}
              {imported.skipped ? `, skipped ${imported.skipped} empty row(s)` : ''}.
            </p>
          ) : null}
        </div>
      </div>
    </Sheet>
  )
}
