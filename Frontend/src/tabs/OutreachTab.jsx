import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useJobStream } from '../lib/useJobStream'
import Console from '../components/Console'
import {
  Button,
  Disclosure,
  Empty,
  Field,
  Input,
  Metric,
  Note,
  PageHead,
  Section,
  Select,
  Status,
  Switch,
  Table,
  Td,
  Tr,
} from '../components/ui'

/*
  Outreach — every path that sends email, in one place.

  Founder outreach used to live as a third card on the Agent screen while the
  company mailing list lived on its own tab, so "send an email" meant two
  different screens depending on which list you had in mind. They are the same
  job and now share a page.
*/

const SEND_TONE = { Applied: 'ok', Interview: 'accent', Offer: 'accent', Failed: 'bad', Skipped: 'warn' }

function timeAgo(iso) {
  if (!iso) return ''
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`
  return `${Math.round(secs / 86400)}d ago`
}

export default function OutreachTab() {
  const [csv, setCsv] = useState(null)
  const [activity, setActivity] = useState(null)
  const [agent, setAgent] = useState(null)
  const [error, setError] = useState('')

  // Founder outreach (agent)
  const [emailLimit, setEmailLimit] = useState(10)
  const [emailDelay, setEmailDelay] = useState(90)
  const [emailDry, setEmailDry] = useState(true)
  const [emailToSelf, setEmailToSelf] = useState(false)
  const [attach, setAttach] = useState(true)

  // Company list (CSV pipeline)
  const [dryRun, setDryRun] = useState(true)
  const [toSelf, setToSelf] = useState(false)
  const [limit, setLimit] = useState(5)
  const [delay, setDelay] = useState(60)
  const [vertical, setVertical] = useState('')

  const [openTasks, setOpenTasks] = useState(false)
  const [openContacts, setOpenContacts] = useState(false)

  // Warm Referral & Alumni outreach
  const [alumniCompany, setAlumniCompany] = useState('')
  const [alumniRole, setAlumniRole] = useState('')
  const [alumniContact, setAlumniContact] = useState('')
  const [alumniSchool, setAlumniSchool] = useState('FAST-NUCES')
  const [alumniSkills, setAlumniSkills] = useState('Full Stack & AI Development')
  const [alumniResults, setAlumniResults] = useState(null)
  const [alumniLoading, setAlumniLoading] = useState(false)
  const [alumniVariant, setAlumniVariant] = useState('alumni')
  const [copiedKey, setCopiedKey] = useState('')

  const handleGenerateAlumni = async () => {
    if (!alumniCompany || !alumniRole) return
    setAlumniLoading(true)
    setError('')
    try {
      const res = await api.getAlumniReferrals({
        companyName: alumniCompany,
        roleTitle: alumniRole,
        contactName: alumniContact || 'there',
        almaMater: alumniSchool || 'FAST-NUCES',
        skillsHighlight: alumniSkills || 'Full Stack & AI Development',
      })
      if (res?.ok) {
        setAlumniResults(res.data)
      }
    } catch (e) {
      setError(e.message || 'Could not generate referral templates.')
    } finally {
      setAlumniLoading(false)
    }
  }

  const handleCopy = (text, key) => {
    navigator.clipboard.writeText(text)
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(''), 2000)
  }

  const refresh = useCallback(async () => {
    try {
      const [o, a, ag] = await Promise.all([
        api.overview(),
        api.activity(),
        api.agentOverview().catch(() => null),
      ])
      setCsv(o)
      setActivity(a)
      setAgent(ag)
      return o
    } catch (e) {
      setError(e.message)
      return null
    }
  }, [])

  // One SSE implementation for the whole app. This tab used to hand-roll
  // its own EventSource handling, line for line the same as the hook.
  const stream = useJobStream(refresh)

  useEffect(() => {
    refresh().then((o) => {
      if (o?.activeJob) stream.view(o.activeJob)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh])

  useEffect(() => {
    if (stream.job?.status !== 'running') return
    const id = setInterval(refresh, 8000)
    return () => clearInterval(id)
  }, [stream.job?.status, refresh])

  const run = (key, payload = {}) => stream.start({ key, ...payload })

  if (!csv) return <Empty title="Loading" />

  const stats = csv.stats
  const env = csv.environment
  const starting = stream.starting
  const busy = stream.busy || !!starting
  const tasks = csv.tasks?.filter((t) => t.key !== 'send') || []
  const verified =
    (agent?.stats?.peopleByStatus?.valid || 0) + (agent?.stats?.peopleByStatus?.risky || 0)

  return (
    <div className="space-y-4">
      <PageHead
        title="Outreach"
        description="Cold email, from two lists: founders and recruiters the agent verified, and your own company dataset."
      />

      {error ? (
        <Note tone="bad" title="Something went wrong" onDismiss={() => setError('')}>
          {error}
        </Note>
      ) : null}

      {env && !env.gmailPasswordSet ? (
        <Note tone="warn" title="Gmail app password not configured">
          <code className="text-n-200">GMAIL_APP_PASS</code> is missing from{' '}
          <code className="text-n-200">.env</code>. Dry runs work; real sends fail at SMTP login.
        </Note>
      ) : null}

      {/* ------------------------------------------- warm referral & alumni */}
      <Section
        title="Alumni & warm referrals"
        description="Generate high-converting personalized pitches anchored on your university (FAST-NUCES) and tech stack synergy."
        actions={<Status tone="ok">5x-10x callback</Status>}
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Company" hint="e.g. Linear, Motive, Stripe">
            <Input
              placeholder="Target Company"
              value={alumniCompany}
              onChange={(e) => setAlumniCompany(e.target.value)}
            />
          </Field>
          <Field label="Target role" hint="e.g. Full Stack Engineer">
            <Input
              placeholder="Role Title"
              value={alumniRole}
              onChange={(e) => setAlumniRole(e.target.value)}
            />
          </Field>
          <Field label="Contact name (optional)" hint="e.g. Sarah / Ali">
            <Input
              placeholder="Contact Name"
              value={alumniContact}
              onChange={(e) => setAlumniContact(e.target.value)}
            />
          </Field>
          <Field label="Alma mater" hint="Alumni anchor">
            <Input
              placeholder="FAST-NUCES"
              value={alumniSchool}
              onChange={(e) => setAlumniSchool(e.target.value)}
            />
          </Field>
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          <Button
            variant="primary"
            disabled={!alumniCompany || !alumniRole || alumniLoading}
            busy={alumniLoading}
            onClick={handleGenerateAlumni}
          >
            Generate 3 warm pitches
          </Button>
          <span className="text-tiny text-n-500">
            Generates Alumni Anchor, Engineering Peer, and Direct Lead variations.
          </span>
        </div>

        {alumniResults ? (
          <div className="mt-4 space-y-3 rounded-md border border-line bg-surface p-4">
            <div className="flex flex-wrap items-center gap-2 border-b border-line pb-3">
              {Object.entries(alumniResults.variants).map(([key, item]) => (
                <button
                  key={key}
                  onClick={() => setAlumniVariant(key)}
                  className={`press rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                    alumniVariant === key ? 'bg-n-800 text-n-100' : 'text-n-400 hover:text-n-200'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {alumniResults.variants[alumniVariant] ? (
              <div className="space-y-2 pt-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-n-300">
                    Subject: {alumniResults.variants[alumniVariant].subject}
                  </span>
                  <Button
                    variant="subtle"
                    size="sm"
                    onClick={() =>
                      handleCopy(
                        `${alumniResults.variants[alumniVariant].subject}\n\n${alumniResults.variants[alumniVariant].body}`,
                        alumniVariant,
                      )
                    }
                  >
                    {copiedKey === alumniVariant ? '✓ Copied' : 'Copy Pitch'}
                  </Button>
                </div>
                <pre className="whitespace-pre-wrap rounded-md bg-n-900 p-3 font-sans text-xs leading-relaxed text-n-300">
                  {alumniResults.variants[alumniVariant].body}
                </pre>
              </div>
            ) : null}
          </div>
        ) : null}
      </Section>

      {/* ------------------------------------------------- founder outreach */}
      <Section
        title="Verified contacts"
        description={
          agent
            ? `${verified} founder and recruiter address${verified === 1 ? '' : 'es'} the agent found and verified.`
            : 'The agent is not reachable, so this list is unavailable.'
        }
        actions={
          emailDry ? (
            <Status tone="info">dry run</Status>
          ) : emailToSelf ? (
            <Status tone="warn">to yourself</Status>
          ) : (
            <Status tone="bad">live send</Status>
          )
        }
      >
        <div className="grid gap-4 sm:grid-cols-[repeat(2,minmax(0,180px))_minmax(0,1fr)] sm:items-start">
          <Field label="Emails" hint="Max this run.">
            <Input
              type="number"
              min={1}
              max={100}
              value={emailLimit}
              onChange={(e) => setEmailLimit(e.target.value)}
            />
          </Field>
          <Field label="Delay" hint="Seconds between sends.">
            <Input
              type="number"
              min={0}
              max={3600}
              value={emailDelay}
              onChange={(e) => setEmailDelay(e.target.value)}
            />
          </Field>
          <div className="space-y-2.5 sm:pt-5">
            <Switch checked={emailDry} onChange={setEmailDry} label="Dry run" />
            <Switch
              checked={emailToSelf}
              onChange={setEmailToSelf}
              disabled={emailDry}
              label="Send to myself"
            />
            <Switch checked={attach} onChange={setAttach} label="Attach resume" />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Button
            variant="primary"
            disabled={busy || !verified}
            busy={starting === 'agent_outreach'}
            onClick={() =>
              run('agent_outreach', {
                limit: Number(emailLimit),
                delay: Number(emailDelay),
                dry_run: emailDry,
                to_self: emailToSelf,
                no_attach: !attach,
              })
            }
          >
            {emailDry ? 'Draft emails' : `Send ${emailLimit}`}
          </Button>
          {!verified ? (
            <span className="text-tiny text-n-500">
              No verified contacts yet. Run a search on the Jobs page with email discovery on.
            </span>
          ) : null}
        </div>
      </Section>

      {/* ----------------------------------------------------- company list */}
      <Section
        title="Company list"
        description={`${stats?.total ?? 0} companies from companies_dataset.csv, ${stats?.readyToSend ?? 0} ready to contact.`}
        actions={
          dryRun ? (
            <Status tone="info">dry run</Status>
          ) : toSelf ? (
            <Status tone="warn">to yourself</Status>
          ) : (
            <Status tone="bad">live send</Status>
          )
        }
      >
        <dl className="mb-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Metric label="Applied" value={stats?.statuses?.Applied ?? 0} />
          <Metric label="Pending" value={stats?.statuses?.Pending ?? 0} />
          <Metric label="Failed" value={stats?.statuses?.Failed ?? 0} />
          <Metric label="Ready" value={stats?.readyToSend ?? 0} />
        </dl>

        <div className="grid gap-4 sm:grid-cols-[repeat(2,minmax(0,140px))_minmax(0,1fr)] sm:items-start">
          <Field label="Limit" hint="Gmail caps near 500/day.">
            <Input
              type="number"
              min={1}
              max={500}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
            />
          </Field>
          <Field label="Delay" hint="Seconds between sends.">
            <Input
              type="number"
              min={0}
              max={3600}
              value={delay}
              onChange={(e) => setDelay(e.target.value)}
            />
          </Field>
          <Field label="Vertical" hint="Leave as all to work through the list in order.">
            <Select value={vertical} onChange={(e) => setVertical(e.target.value)}>
              <option value="">All verticals</option>
              {(csv.verticals || []).map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="mt-4 space-y-2.5">
          <Switch checked={dryRun} onChange={setDryRun} label="Dry run" />
          <Switch
            checked={toSelf}
            onChange={setToSelf}
            disabled={dryRun}
            label="Route everything to myself"
            hint="Real SMTP send with every recipient replaced by your address."
          />
        </div>

        {!dryRun && !toSelf ? (
          <div className="mt-4">
            <Note tone="bad" title="This sends real email">
              {limit} message{limit == 1 ? '' : 's'} go out to real companies, {delay}s apart, and the
              CSV is marked Applied.
            </Note>
          </div>
        ) : null}

        <div className="mt-4">
          <Button
            variant="primary"
            disabled={busy}
            busy={starting === 'send'}
            onClick={() =>
              run('send', {
                dry_run: dryRun,
                to_self: toSelf,
                limit: Number(limit),
                delay: Number(delay),
                vertical: vertical || null,
              })
            }
          >
            {dryRun ? 'Preview' : toSelf ? 'Send to myself' : `Send ${limit}`}
          </Button>
        </div>
      </Section>

      <Console lines={stream.lines} job={stream.job} onStop={stream.stop} onClear={stream.clear} />

      {/* ---------------------------------------------------------- history */}
      <Section title="Recent sends" description="Every attempt, newest first." flush>
        <Table
          columns={[
            { label: 'Status' },
            { label: 'Company' },
            { label: 'To' },
            { label: 'When', className: 'text-right' },
          ]}
          rows={(activity?.sends || []).slice(0, 25)}
          maxHeight="max-h-80"
          empty={<Empty title="No sends yet" />}
          renderRow={(s, i) => (
            <Tr key={i}>
              <Td>
                <Status tone={SEND_TONE[s.status] || 'neutral'}>{s.status}</Status>
              </Td>
              <Td className="text-n-200">{s.company}</Td>
              <Td className="text-n-500">{s.to}</Td>
              <Td className="text-right whitespace-nowrap text-n-500">{timeAgo(s.at)}</Td>
            </Tr>
          )}
        />
      </Section>

      <Disclosure
        title="Verified contact list"
        description="Addresses the agent found, with how each one was checked."
        open={openContacts}
        onToggle={setOpenContacts}
      >
        <ContactList />
      </Disclosure>

      <Disclosure
        title="Pipeline tasks"
        description="Rebuild the company dataset by crawling each site."
        open={openTasks}
        onToggle={setOpenTasks}
        actions={
          <div className="flex items-center gap-3">
            <Status tone={env?.envFilePresent ? 'ok' : 'bad'}>.env</Status>
            <Status tone={stats?.csvPresent ? 'ok' : 'bad'}>dataset</Status>
          </div>
        }
      >
        <ul className="divide-y divide-line">
          {tasks.map((t) => (
            <li key={t.key} className="flex items-start gap-4 py-3 first:pt-0 last:pb-0">
              <div className="min-w-0 flex-1">
                <p className="text-sm text-n-200">{t.label}</p>
                <p className="mt-0.5 text-tiny leading-relaxed text-n-500">{t.description}</p>
              </div>
              <Button size="sm" disabled={busy} busy={starting === t.key} onClick={() => run(t.key)}>
                Run
              </Button>
            </li>
          ))}
        </ul>
      </Disclosure>
    </div>
  )
}

const EMAIL_TONE = { valid: 'ok', risky: 'warn', invalid: 'bad', unknown: 'neutral' }

function ContactList() {
  const [rows, setRows] = useState(null)

  useEffect(() => {
    api
      .agentData('people', 100)
      .then((d) => setRows(d.rows))
      .catch(() => setRows([]))
  }, [])

  if (!rows) return <p className="text-tiny text-n-500">Loading</p>

  return (
    <Table
      columns={[
        { label: 'Email' },
        { label: 'Name' },
        { label: 'Company' },
        { label: 'Verified' },
      ]}
      rows={rows}
      maxHeight="max-h-96"
      empty={<p className="text-tiny text-n-500">No contacts found yet.</p>}
      renderRow={(p, i) => (
        <Tr key={i}>
          <Td className="text-n-200">{p.email}</Td>
          <Td className="text-n-400">
            {p.full_name || '—'}
            {p.role ? <span className="text-n-500"> · {p.role}</span> : null}
          </Td>
          <Td className="text-n-400">{p.company_name || '—'}</Td>
          <Td>
            <Status tone={EMAIL_TONE[p.email_status] || 'neutral'} title={p.verify_detail || ''}>
              {p.email_status}
            </Status>
          </Td>
        </Tr>
      )}
    />
  )
}
