import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { uploadEvidence } from "@/services/evidence";

export default function Upload() {
  const [caseId, setCaseId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (vars: { caseId: string; file: File }) =>
      uploadEvidence(vars.caseId, vars.file),
    onSuccess: (data) => {
      setResult(
        `Evidência ${data.id} enviada com sucesso!\nTipo: ${data.file_type}\nSHA-256: ${data.sha256}`
      );
    },
    onError: (err: Error) => {
      setResult(`Erro: ${err.message}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setResult(null);
    if (!file || !caseId) {
      setResult("Preencha todos os campos");
      return;
    }
    mutation.mutate({ caseId, file });
  };

  return (
    <div className="upload-page">
      <h2>Upload de Evidência</h2>

      <form onSubmit={handleSubmit} className="card">
        <div className="form-group">
          <label htmlFor="caseId">ID do Caso</label>
          <input
            id="caseId"
            type="text"
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
            required
            placeholder="ID do caso"
          />
        </div>

        <div className="form-group">
          <label htmlFor="file">Arquivo</label>
          <input
            id="file"
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            required
            accept="image/*,audio/*,video/*,application/pdf"
          />
          {file && (
            <small>
              {file.name} — {(file.size / 1024 / 1024).toFixed(2)} MB
            </small>
          )}
        </div>

        <button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Enviando..." : "Enviar Evidência"}
        </button>
      </form>

      {result && (
        <div className="card result-card">
          <h3>Resultado</h3>
          <pre>{result}</pre>
        </div>
      )}
    </div>
  );
}
