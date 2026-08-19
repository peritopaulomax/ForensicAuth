interface Props {
  page: number;
  pageCount: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export default function EvidenceListPagination({
  page,
  pageCount,
  total,
  pageSize,
  onPageChange,
}: Props) {
  if (total <= pageSize) return null;

  const from = page * pageSize + 1;
  const to = Math.min(total, (page + 1) * pageSize);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "0.75rem",
        flexWrap: "wrap",
        marginBottom: "0.75rem",
        fontSize: "0.8rem",
        color: "#6b7280",
      }}
    >
      <span>
        Exibindo {from}–{to} de {total}
      </span>
      <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
        <button
          type="button"
          disabled={page <= 0}
          onClick={() => onPageChange(page - 1)}
          style={navBtnStyle(page <= 0)}
        >
          Anterior
        </button>
        <span style={{ minWidth: "6rem", textAlign: "center", color: "#374151" }}>
          Pagina {page + 1} / {pageCount}
        </span>
        <button
          type="button"
          disabled={page >= pageCount - 1}
          onClick={() => onPageChange(page + 1)}
          style={navBtnStyle(page >= pageCount - 1)}
        >
          Proxima
        </button>
      </div>
    </div>
  );
}

function navBtnStyle(disabled: boolean) {
  return {
    padding: "0.3rem 0.65rem",
    background: disabled ? "#f3f4f6" : "#fff",
    color: disabled ? "#9ca3af" : "#374151",
    border: "1px solid #e5e7eb",
    borderRadius: "4px",
    cursor: disabled ? "not-allowed" : "pointer",
    fontSize: "0.78rem",
  } as const;
}
