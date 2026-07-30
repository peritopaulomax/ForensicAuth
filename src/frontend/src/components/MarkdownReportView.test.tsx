import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MarkdownReportView from "@/components/MarkdownReportView";

describe("MarkdownReportView", () => {
  it("renders headings and tables from markdown", () => {
    const md = [
      "# Relatorio tecnico",
      "",
      "| Item | Resultado |",
      "|---|---|",
      "| Integridade | **Integra** |",
      "",
      "> Aviso metodologico",
      "",
      "- Achado um",
    ].join("\n");

    render(<MarkdownReportView content={md} />);

    expect(screen.getByRole("heading", { level: 1, name: "Relatorio tecnico" })).toBeInTheDocument();
    expect(screen.getByText("Integra")).toBeInTheDocument();
    expect(screen.getByText("Aviso metodologico")).toBeInTheDocument();
    expect(screen.getByText("Achado um")).toBeInTheDocument();
  });

  it("renders fenced code blocks with readable contrast (not inline chips)", () => {
    const md = [
      "### 3.1.2 Integridade",
      "",
      "```",
      "SHA-256 do ByteRange: abc123",
      "messageDigest: abc123",
      "→ IDÊNTICOS",
      "```",
      "",
      "Verificação da assinatura: **válida**",
    ].join("\n");

    const { container } = render(<MarkdownReportView content={md} />);
    const pre = container.querySelector("pre");
    expect(pre).toBeTruthy();
    const code = pre?.querySelector("code");
    expect(code).toBeTruthy();
    expect(code?.textContent).toContain("SHA-256 do ByteRange");
    // Must not paint light "chip" background on block code
    expect((code as HTMLElement).style.backgroundColor || (code as HTMLElement).style.background).toMatch(
      /transparent|^$/i
    );
    expect((code as HTMLElement).style.color).toMatch(/#e2e8f0|rgb\(226,\s*232,\s*240\)/i);
  });

  it("keeps long inline hashes dark on light background", () => {
    const hash = "F".repeat(128);
    const md = `**SHA-512 do arquivo:** \`${hash}\``;
    const { container } = render(<MarkdownReportView content={md} />);
    const code = container.querySelector("code");
    expect(code).toBeTruthy();
    expect(code?.parentElement?.tagName).not.toBe("PRE");
    expect((code as HTMLElement).style.color).toMatch(/#0f172a|rgb\(15,\s*23,\s*42\)/i);
    expect((code as HTMLElement).style.backgroundColor || (code as HTMLElement).style.background).toMatch(
      /#e2e8f0|rgb\(226,\s*232,\s*240\)/i
    );
  });

  it("shows loading and empty states", () => {
    const { rerender } = render(<MarkdownReportView content="" loading />);
    expect(screen.getByText("Carregando…")).toBeInTheDocument();

    rerender(<MarkdownReportView content="" />);
    expect(screen.getByText("(sem conteudo)")).toBeInTheDocument();
  });
});
