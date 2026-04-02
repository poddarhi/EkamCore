export default function Dashboard() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        gap: 12,
        color: "#e8e8ea",
      }}
    >
      <h1 style={{ fontSize: 24, fontWeight: 600 }}>EkamCore Manager</h1>
      <p style={{ color: "#71717a", fontSize: 14 }}>
        Dashboard — S04-001 (Health tiles, service status) coming in Sprint 4.
      </p>
    </div>
  );
}
