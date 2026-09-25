import { ItemStat } from "./api";

// Filled in by the AI stage: explains why the class chose what it chose, from
// the question on the master sheet and the numbers above.
export default function AiPanel({ examUuid, item }: { examUuid: string; item: ItemStat }) {
  void examUuid;
  return (
    <div className="card">
      <h2>AI 解釋 <span>第 {item.question_no} 題</span></h2>
      <div className="note">即將推出：AI 會讀題目，說明大家為什麼選這個答案。</div>
    </div>
  );
}
