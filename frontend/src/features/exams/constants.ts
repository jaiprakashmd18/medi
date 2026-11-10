import type { QuestionType } from "@/types/api";

export const TYPE_LABELS: Record<QuestionType, string> = {
  sba: "Single best answer", multi: "Multiple select", true_false: "True / false", fill_blank: "Fill in the blank",
  short: "Short answer", long: "Long answer", viva: "Viva / oral", diagram: "Diagram identification",
};
