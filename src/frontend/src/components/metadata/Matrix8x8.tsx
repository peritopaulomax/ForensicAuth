export default function Matrix8x8({ matrix, title }: { matrix: number[][]; title?: string }) {
  if (!matrix?.length) return null;
  return (
    <div className="jpeg-structure-mini-card">
      {title && <h5 className="jpeg-structure-mini-card__title">{title}</h5>}
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", fontSize: "0.78rem", width: "100%" }}>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={i}>
                {row.map((val, j) => (
                  <td
                    key={j}
                    style={{
                      border: "1px solid #d1d5db",
                      padding: "0.35rem 0.45rem",
                      textAlign: "center",
                      background: val === 0 ? "#f3f4f6" : "#fff",
                      minWidth: 30,
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    {val}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
