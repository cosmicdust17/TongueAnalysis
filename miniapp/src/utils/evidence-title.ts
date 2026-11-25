import type { Evidence, TextbookReading } from "@/types";

const excerptTopics: [RegExp, string][] = [
  [/口腔对舌象的影响|缺牙[^。]{0,40}舌苔/, "口腔与舌象"],
  [/舌苔和舌质均出现异常|舌苔与舌质综合/, "舌苔与舌质"],
  [/舌面上所附着的苔垢呈现白色|薄白苔[^。]{0,24}厚白苔/, "白苔的厚薄"],
  [/苔薄白而润|薄白润苔/, "薄白润苔"],
  [/口干[，,]?但欲漱水不欲咽|口干而只想漱口却不想咽水/, "口干与漱水"],
];

export function evidenceTitle(source?: Evidence, reading?: TextbookReading) {
  const title = source?.title?.replace(/[《》\s]/g, "") || "";
  const book = source?.source_title?.replace(/[《》\s]/g, "") || "";
  const isBook = (title && book.includes(title)) || /诊断学|教材|手册|参考资料/.test(title);
  if (!isBook && /^[\u3400-\u9fff]{2,8}$/.test(title)) {
    return title.length >= 4 ? title : title + (source?.kind === "症状" ? "表现" : "要点");
  }

  const excerpt = (source?.text || reading?.quote || "").replace(/\s+/g, "");
  const topic = excerptTopics.find(([pattern]) => pattern.test(excerpt));
  return topic?.[1] || "教材段落";
}
