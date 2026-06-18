import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class JpegCompareErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("JPEG compare render error:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            marginTop: "1rem",
            padding: "0.85rem 1rem",
            borderRadius: 8,
            background: "#fef2f2",
            color: "#991b1b",
            fontSize: "0.85rem",
          }}
        >
          <strong>Erro ao exibir a grade de comparação.</strong>
          <p style={{ margin: "0.5rem 0 0" }}>{this.state.error.message}</p>
          <button
            type="button"
            style={{
              marginTop: "0.65rem",
              padding: "0.35rem 0.75rem",
              border: "1px solid #fca5a5",
              borderRadius: 6,
              background: "#fff",
              cursor: "pointer",
            }}
            onClick={() => this.setState({ error: null })}
          >
            Tentar novamente
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
