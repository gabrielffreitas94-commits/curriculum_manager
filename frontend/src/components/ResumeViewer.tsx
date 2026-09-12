"use client";

import React from "react";
import { ResumeGenerateResponse } from "@/types";
import { ApiClient } from "@/lib/api";
import {
  Download,
  FileText,
  Building,
  GraduationCap,
  Award,
  Languages,
  Mail,
  Phone,
  MapPin,
  ExternalLink,
  Sparkles,
  Loader2,
  AlertCircle,
} from "lucide-react";

/**
 * Propriedades do componente ResumeViewer.
 *
 * @interface ResumeViewerProps
 * @property {ResumeGenerateResponse} resume - Dados estruturados do currículo gerado via Gemini com validação anti-alucinação.
 * @property {() => void} [onClose] - Callback opcional para fechar a visualização.
 *
 * @a11y
 * - Apresenta estrutura semântica hierárquica (`<h1>` para o nome do candidato, `<h2>` para seções como Experiência e Educação).
 * - Links externos possuem `aria-label` descritivos e atributos `rel="noopener noreferrer"`.
 * - Os botões de download utilizam requisições autenticadas com Bearer token e Blob para impedir vazamento de credenciais e erros 401.
 * - Estados de carregamento são anunciados via `aria-busy` e feedback de erro acessível via `role="alert"` e `aria-live="polite"`.
 */
export interface ResumeViewerProps {
  resume: ResumeGenerateResponse;
  onClose?: () => void;
}

export const ResumeViewer: React.FC<ResumeViewerProps> = ({ resume, onClose }) => {
  const { structured_content, match_percentage, version_number, resume_id } = resume;
  const {
    header,
    professional_summary,
    selected_experiences,
    skills_highlighted,
    education,
    certifications,
    languages,
  } = structured_content;

  const [downloadingFormat, setDownloadingFormat] = React.useState<"pdf" | "docx" | null>(null);
  const [downloadError, setDownloadError] = React.useState<string | null>(null);

  const handleDownload = async (format: "pdf" | "docx") => {
    try {
      setDownloadingFormat(format);
      setDownloadError(null);
      await ApiClient.downloadExport(resume_id, format);
    } catch (err) {
      setDownloadError(
        err instanceof Error
          ? err.message
          : `Falha ao baixar currículo em formato ${format.toUpperCase()}.`
      );
    } finally {
      setDownloadingFormat(null);
    }
  };

  return (
    <div
      className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden flex flex-col"
      role="region"
      aria-label="Visualização do Currículo Sintetizado"
    >
      {/* Barra de Ações Superior */}
      <div className="bg-slate-50 dark:bg-slate-800/80 p-4 border-b border-slate-200 dark:border-slate-700 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 text-xs font-semibold">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Versão v{version_number} &bull; Aderência {match_percentage}%
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleDownload("pdf")}
            disabled={downloadingFormat !== null}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-xs font-bold shadow-xs transition focus:outline-hidden focus:ring-2 focus:ring-red-500 cursor-pointer disabled:cursor-not-allowed"
            aria-label="Exportar e baixar currículo em formato PDF com diagramação ATS"
            aria-busy={downloadingFormat === "pdf"}
          >
            {downloadingFormat === "pdf" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <>
                <FileText className="h-4 w-4" aria-hidden="true" />
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
              </>
            )}
            <span>{downloadingFormat === "pdf" ? "Baixando PDF..." : "Baixar PDF (ATS)"}</span>
          </button>

          <button
            type="button"
            onClick={() => handleDownload("docx")}
            disabled={downloadingFormat !== null}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-bold shadow-xs transition focus:outline-hidden focus:ring-2 focus:ring-blue-500 cursor-pointer disabled:cursor-not-allowed"
            aria-label="Exportar e baixar currículo editável em formato Word DOCX"
            aria-busy={downloadingFormat === "docx"}
          >
            {downloadingFormat === "docx" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <>
                <FileText className="h-4 w-4" aria-hidden="true" />
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
              </>
            )}
            <span>{downloadingFormat === "docx" ? "Baixando DOCX..." : "Baixar DOCX"}</span>
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-2 text-xs font-medium rounded-lg text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700 transition cursor-pointer"
            >
              Fechar
            </button>
          )}
        </div>
      </div>

      {/* Alerta Acessível de Falha no Download */}
      {downloadError && (
        <div
          role="alert"
          aria-live="polite"
          className="bg-red-50 dark:bg-red-950/60 border-b border-red-200 dark:border-red-900/60 px-4 py-2.5 text-xs text-red-700 dark:text-red-300 flex items-center justify-between gap-2"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-red-500" aria-hidden="true" />
            <span>{downloadError}</span>
          </div>
          <button
            type="button"
            onClick={() => setDownloadError(null)}
            className="text-red-600 hover:text-red-800 dark:hover:text-red-200 text-xs font-semibold underline cursor-pointer"
            aria-label="Fechar mensagem de erro de download"
          >
            Fechar
          </button>
        </div>
      )}

      {/* Folha do Currículo (Estilo ATS Single-Column) */}
      <div className="p-8 sm:p-12 max-w-4xl mx-auto w-full space-y-6 text-slate-800 dark:text-slate-200">
        {/* Header do Candidato */}
        <header className="border-b-2 border-slate-800 dark:border-slate-300 pb-4 text-center sm:text-left">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {header.full_name}
          </h1>
          {header.target_title && (
            <p className="text-base font-semibold text-indigo-600 dark:text-indigo-400 mt-1">
              {header.target_title}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-center sm:justify-start gap-3 mt-3 text-xs text-slate-600 dark:text-slate-400">
            {header.email && (
              <span className="flex items-center gap-1">
                <Mail className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                {header.email}
              </span>
            )}
            {header.phone && (
              <span className="flex items-center gap-1">
                <Phone className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                {header.phone}
              </span>
            )}
            {header.location && (
              <span className="flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                {header.location}
              </span>
            )}
            {header.links &&
              Object.entries(header.links).map(([platform, link]) => (
                <a
                  key={platform}
                  href={link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-indigo-600 dark:text-indigo-400 hover:underline capitalize"
                  aria-label={`Perfil em ${platform} (abre em nova aba)`}
                >
                  <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  {platform}
                </a>
              ))}
          </div>
        </header>

        {/* Resumo Profissional */}
        {professional_summary && (
          <section aria-labelledby="section-summary">
            <h2
              id="section-summary"
              className="text-sm font-bold uppercase tracking-wider text-slate-900 dark:text-slate-100 border-b border-slate-200 dark:border-slate-800 pb-1 mb-2"
            >
              Resumo Profissional
            </h2>
            <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
              {professional_summary}
            </p>
          </section>
        )}

        {/* Competências em Destaque */}
        {skills_highlighted && skills_highlighted.length > 0 && (
          <section aria-labelledby="section-skills">
            <h2
              id="section-skills"
              className="text-sm font-bold uppercase tracking-wider text-slate-900 dark:text-slate-100 border-b border-slate-200 dark:border-slate-800 pb-1 mb-2"
            >
              Competências Chave (ATS)
            </h2>
            <div className="flex flex-wrap gap-1.5" role="list">
              {skills_highlighted.map((skill, i) => (
                <span
                  key={i}
                  role="listitem"
                  className="px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 text-xs font-medium text-slate-800 dark:text-slate-200"
                >
                  {skill}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Experiências Profissionais Selecionadas */}
        {selected_experiences && selected_experiences.length > 0 && (
          <section aria-labelledby="section-experience">
            <h2
              id="section-experience"
              className="text-sm font-bold uppercase tracking-wider text-slate-900 dark:text-slate-100 border-b border-slate-200 dark:border-slate-800 pb-1 mb-3 flex items-center gap-1.5"
            >
              <Building className="h-4 w-4 text-slate-500" aria-hidden="true" />
              <span>Experiência Profissional Relevante</span>
            </h2>
            <div className="space-y-4">
              {selected_experiences.map((exp, idx) => (
                <article key={idx} className="space-y-1.5">
                  <div className="flex flex-wrap items-baseline justify-between gap-1">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                      {exp.position_title}{" "}
                      <span className="font-normal text-slate-500">
                        &bull; {exp.company_name}
                      </span>
                    </h3>
                    <span className="text-xs text-slate-500 font-medium">
                      {exp.start_date} &ndash;{" "}
                      {exp.is_current ? "Presente" : exp.end_date || "Atual"}
                    </span>
                  </div>

                  {exp.bullet_points && exp.bullet_points.length > 0 && (
                    <ul className="list-disc list-inside space-y-1 text-xs sm:text-sm text-slate-700 dark:text-slate-300">
                      {exp.bullet_points.map((bp, bIdx) => (
                        <li key={bIdx} className="leading-relaxed">
                          {bp}
                        </li>
                      ))}
                    </ul>
                  )}

                  {exp.tech_stack && exp.tech_stack.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1 pt-1">
                      <span className="text-[11px] font-semibold text-slate-500">
                        Tecnologias:
                      </span>
                      {exp.tech_stack.map((tech, tIdx) => (
                        <span
                          key={tIdx}
                          className="px-1.5 py-0.5 rounded text-[11px] bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300"
                        >
                          {tech}
                        </span>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>
        )}

        {/* Formação Acadêmica */}
        {education && education.length > 0 && (
          <section aria-labelledby="section-education">
            <h2
              id="section-education"
              className="text-sm font-bold uppercase tracking-wider text-slate-900 dark:text-slate-100 border-b border-slate-200 dark:border-slate-800 pb-1 mb-2 flex items-center gap-1.5"
            >
              <GraduationCap className="h-4 w-4 text-slate-500" aria-hidden="true" />
              <span>Formação Acadêmica</span>
            </h2>
            <div className="space-y-2">
              {education.map((edu, idx) => (
                <div key={idx} className="flex justify-between items-baseline text-xs sm:text-sm">
                  <div>
                    <span className="font-bold text-slate-900 dark:text-slate-100">
                      {edu.degree}
                    </span>{" "}
                    &bull; {edu.institution}
                  </div>
                  {edu.end_date && (
                    <span className="text-xs text-slate-500">{edu.end_date}</span>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Certificações & Idiomas */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          {certifications && certifications.length > 0 && (
            <section aria-labelledby="section-certifications">
              <h2
                id="section-certifications"
                className="text-sm font-bold uppercase tracking-wider text-slate-900 dark:text-slate-100 border-b border-slate-200 dark:border-slate-800 pb-1 mb-2 flex items-center gap-1.5"
              >
                <Award className="h-4 w-4 text-slate-500" aria-hidden="true" />
                <span>Certificações</span>
              </h2>
              <ul className="space-y-1 text-xs sm:text-sm" role="list">
                {certifications.map((c, idx) => (
                  <li key={idx} className="text-slate-700 dark:text-slate-300">
                    <span className="font-semibold">{c.name}</span>
                    {c.issuer && <span className="text-slate-500"> &bull; {c.issuer}</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {languages && languages.length > 0 && (
            <section aria-labelledby="section-languages">
              <h2
                id="section-languages"
                className="text-sm font-bold uppercase tracking-wider text-slate-900 dark:text-slate-100 border-b border-slate-200 dark:border-slate-800 pb-1 mb-2 flex items-center gap-1.5"
              >
                <Languages className="h-4 w-4 text-slate-500" aria-hidden="true" />
                <span>Idiomas</span>
              </h2>
              <ul className="space-y-1 text-xs sm:text-sm" role="list">
                {languages.map((l, idx) => (
                  <li key={idx} className="text-slate-700 dark:text-slate-300">
                    <span className="font-semibold">{l.language}</span>:{" "}
                    <span className="text-slate-500">{l.proficiency}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
};
