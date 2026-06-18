import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { listTechniques, submitJob } from "@/services/analysis";

export default function Analysis() {
  const [evidenceId, setEvidenceId] = useState("");
  const [technique, setTechnique] = useState("");
  const [parameters, setParameters] = useState("{}");
  const [result, setResult] = useState<string | null>(null);

  const { data: techniques, isLoading } = useQuery({
    queryKey: ["techniques"],
    queryFn: listTechniques,
  });

  const mutation = useMutation({
    mutationFn: submitJob,
    onSuccess: (data) => {
      setResult(`Job ${data.id} criado com status: ${data.status}`);
    },
    onError: (err: Error) => {
      setResult(`Erro: ${err.message}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setResult(null);
    let parsedParams = {};
    try {
      parsedParams = JSON.parse(parameters);
    } catch {
      setResult("Erro: parâmetros JSON inválidos");
      return;
    }
    mutation.mutate({
      evidence_id: evidenceId,
      technique,
      parameters: parsedParams,
    });
  };

  return (
    <div className="analysis-page">
      <h2>Nova Análise Forense</h2>

      <form onSubmit={handleSubmit} className="card">
        <div className="form-group">
          <label htmlFor="evidenceId">ID da Evidência</label>
          <input
            id="evidenceId"
            type="text"
            value={evidenceId}
            onChange={(e) => setEvidenceId(e.target.value)}
            required
            placeholder="UUID da evidência"
          />
        </div>

        <div className="form-group">
          <label htmlFor="technique">Técnica</label>
          {isLoading ? (
            <p>Carregando...</p>
          ) : (
            <select
              id="technique"
              value={technique}
              onChange={(e) => setTechnique(e.target.value)}
              required
            >
              <option value="">Selecione...</option>
              {techniques?.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="form-group">
          <label htmlFor="parameters">Parâmetros (JSON)</label>
          <textarea
            id="parameters"
            rows={4}
            value={parameters}
            onChange={(e) => setParameters(e.target.value)}
            placeholder='{"qualidade": 85}'
          />
        </div>

        <button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Enviando..." : "Submeter Análise"}
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
