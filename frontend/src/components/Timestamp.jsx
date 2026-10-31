import { exactDate, formatDate } from '../api/operator'

export default function Timestamp({ value, className }) {
  if (!value) return <span className={className}>Не надано</span>
  return <time className={className} dateTime={value} title={exactDate(value)}>{formatDate(value)}</time>
}
