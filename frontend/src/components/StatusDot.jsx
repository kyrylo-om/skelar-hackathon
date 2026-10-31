import { STATUS } from '../api/operator'

export default function StatusDot({ status, children }) {
  const tone = ['resolved', 'approved', 'succeeded', 'pass', 'allow', 'approve', 'done'].includes(status) ? 'success'
    : ['failed', 'rejected', 'reject', 'block', 'deny', 'fail'].includes(status) ? 'danger'
      : ['waiting_operator', 'needs_review', 'pending', 'needs_human', 'warn', 'awaiting_confirmation'].includes(status) ? 'warning' : 'neutral'
  return <span className={`status ${tone}`}>{children || STATUS[status] || status || 'Не надано'}</span>
}
