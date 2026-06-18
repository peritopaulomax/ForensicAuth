/** Matriz 8×8 em div/grid — evita <table> dentro da grade de comparação. */
export default function DqtMatrixGrid({ matrix, title }: { matrix: number[][]; title?: string }) {
  if (!matrix?.length) return null;
  return (
    <div className="jpeg-dqt-matrix">
      {title && <div className="jpeg-dqt-matrix__title">{title}</div>}
      <div className="jpeg-dqt-matrix__grid" role="grid" aria-label={title || "Matriz de quantização"}>
        {matrix.map((row, i) =>
          row.map((val, j) => (
            <div
              key={`${i}-${j}`}
              role="gridcell"
              className={`jpeg-dqt-matrix__cell${val === 0 ? " jpeg-dqt-matrix__cell--zero" : ""}`}
            >
              {val}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
