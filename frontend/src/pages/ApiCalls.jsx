import EmptyState from '../components/EmptyState'

export default function ApiCalls() {
  // TODO(api): expose redacted product calls with transport, timestamps, duration, request/response,
  // correlation IDs and verified signature state. HTTP metadata must not be invented for MCP.
  return <div className="page"><h2>Виклики підключеного продукту</h2><EmptyState kind="unavailable" title="Журнал API calls недоступний">Backend не має endpoint для журналу HTTP або MCP-викликів. Транспорт, метод, адреса, статус, тривалість, підпис і request/response не надані. Секрети має маскувати сервер.</EmptyState></div>
}
