import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ResumeViewer } from "@/components/ResumeViewer";
import { ResumeGenerateResponse } from "@/types";

describe("ResumeViewer Component", () => {
  const mockResume: ResumeGenerateResponse = {
    resume_id: "res-uuid-12345",
    application_id: "app-uuid-12345",
    version_number: 2,
    match_percentage: 91,
    match_analysis: {},
    structured_content: {
      header: {
        full_name: "Ana Dev Silva",
        target_title: "Tech Lead Python",
        email: "ana.silva@thothcvs.ai",
        phone: "+55 11 98888-7777",
        location: "Campinas, SP",
        links: {
          linkedin: "https://linkedin.com/in/anasilva",
          github: "https://github.com/anasilva",
        },
      },
      professional_summary: "Líder técnica especializada em microsserviços escaláveis.",
      skills_highlighted: ["Python", "FastAPI", "Docker", "PostgreSQL"],
      selected_experiences: [
        {
          company_name: "Tech Solutions",
          position_title: "Senior Backend Developer",
          start_date: "2021-03-01",
          end_date: null,
          is_current: true,
          description: "Desenvolvimento de arquitetura de microsserviços.",
          bullet_points: [
            "Reduziu latência em 40% com cache Redis.",
            "Liderou migração para contêineres Docker.",
          ],
          tech_stack: ["Python", "Redis", "FastAPI"],
          quantifiable_results: ["40% redução de latência"],
          sort_order: 0,
        },
      ],
      education: [
        {
          institution: "UNICAMP",
          degree: "Ciência da Computação",
          end_date: "2019-12-01",
        },
      ],
      certifications: [
        {
          name: "AWS Certified Solutions Architect",
          issuer: "Amazon Web Services",
        },
      ],
      languages: [
        {
          language: "Inglês",
          proficiency: "Fluente",
        },
      ],
    },
  };

  const defaultProps = {
    resume: mockResume,
    onClose: vi.fn(),
  };

  it("should render version number and adherence badge", () => {
    render(<ResumeViewer {...defaultProps} />);

    expect(screen.getByText(/versão v2 • aderência 91%/i)).toBeInTheDocument();
  });

  it("should render PDF and DOCX export links with appropriate hrefs", () => {
    render(<ResumeViewer {...defaultProps} />);

    const pdfLink = screen.getByRole("link", { name: /exportar e baixar currículo em formato pdf/i });
    expect(pdfLink).toHaveAttribute("href", expect.stringContaining("/resumes/res-uuid-12345/export/pdf"));
    expect(pdfLink).toHaveAttribute("download", "curriculo_res-uuid-12345.pdf");

    const docxLink = screen.getByRole("link", { name: /exportar e baixar currículo editável em formato word/i });
    expect(docxLink).toHaveAttribute("href", expect.stringContaining("/resumes/res-uuid-12345/export/docx"));
    expect(docxLink).toHaveAttribute("download", "curriculo_res-uuid-12345.docx");
  });

  it("should render candidate header info (name, title, contacts, links)", () => {
    render(<ResumeViewer {...defaultProps} />);

    expect(screen.getByRole("heading", { level: 1, name: "Ana Dev Silva" })).toBeInTheDocument();
    expect(screen.getByText("Tech Lead Python")).toBeInTheDocument();
    expect(screen.getByText("ana.silva@thothcvs.ai")).toBeInTheDocument();
    expect(screen.getByText("+55 11 98888-7777")).toBeInTheDocument();
    expect(screen.getByText("Campinas, SP")).toBeInTheDocument();

    const linkedinLink = screen.getByRole("link", { name: /perfil em linkedin/i });
    expect(linkedinLink).toHaveAttribute("href", "https://linkedin.com/in/anasilva");
  });

  it("should render summary, highlighted skills, and experiences with bullet points", () => {
    render(<ResumeViewer {...defaultProps} />);

    expect(screen.getByText("Resumo Profissional")).toBeInTheDocument();
    expect(screen.getByText("Líder técnica especializada em microsserviços escaláveis.")).toBeInTheDocument();

    expect(screen.getByText("Competências Chave (ATS)")).toBeInTheDocument();
    expect(screen.getAllByText("FastAPI")[0]).toBeInTheDocument();

    expect(screen.getByText("Senior Backend Developer")).toBeInTheDocument();
    expect(screen.getByText(/Tech Solutions/i)).toBeInTheDocument();
    expect(screen.getByText("Reduziu latência em 40% com cache Redis.")).toBeInTheDocument();
  });

  it("should render education, certifications, and languages", () => {
    render(<ResumeViewer {...defaultProps} />);

    expect(screen.getByText("Formação Acadêmica")).toBeInTheDocument();
    expect(screen.getByText(/UNICAMP/i)).toBeInTheDocument();

    expect(screen.getByText("Certificações")).toBeInTheDocument();
    expect(screen.getByText("AWS Certified Solutions Architect")).toBeInTheDocument();

    expect(screen.getByText("Idiomas")).toBeInTheDocument();
    expect(screen.getByText("Inglês")).toBeInTheDocument();
  });

  it("should trigger onClose callback when clicking close button", () => {
    const onClose = vi.fn();
    render(<ResumeViewer {...defaultProps} onClose={onClose} />);

    const closeBtn = screen.getByRole("button", { name: /fechar/i });
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("should render experience with fallback date when not current and end_date is null", () => {
    const resumeWithPastExp: ResumeGenerateResponse = {
      ...mockResume,
      structured_content: {
        ...mockResume.structured_content,
        selected_experiences: [
          {
            company_name: "Legacy Corp",
            position_title: "Junior Dev",
            start_date: "2018-01-01",
            end_date: null,
            is_current: false,
            bullet_points: [],
            tech_stack: [],
            sort_order: 0,
          },
        ],
      },
    };

    render(<ResumeViewer {...defaultProps} resume={resumeWithPastExp} />);
    expect(screen.getByText(/2018-01-01 – Atual/i)).toBeInTheDocument();
  });
});
