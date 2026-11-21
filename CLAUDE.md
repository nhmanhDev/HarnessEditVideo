# CLAUDE.md

Đọc SecondBrain theo đường dẫn trong chỉ dẫn global đã được bộ `_Setup/Setup-SecondBrain.ps1` thiết lập. Nếu chưa có biển trỏ hoặc không đọc được vault, báo thiếu cấu hình; không tự đoán đường dẫn máy.
Sau đó đọc `Rules/AI Repo Rules.md` trong vault trước khi làm việc ở repo code.

## Behavioral guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Quy tắc dự án

- Repo: `HarnessEditVideo` (GitHub: `nhmanhDev/HarnessEditVideo`): harness để Claude Code edit video theo quy trình và phong cách riêng của chủ repo. Đang ở giai đoạn dựng khung; chưa có tính năng chạy được.
- Stack, lệnh chạy/test và các giới hạn riêng: chưa chọn stack (chưa có mã). Test: `node --test`. Kiểm chuẩn: `node scripts/check-standard.mjs .`.
- Luật chung (git, docs, UI, tên) nằm ở SecondBrain: `Rules/AI Repo Rules.md`; không sao chép dài vào đây. Mấy điều sau áp dụng ngay cả khi không đọc được vault:
  - Xong việc chạy `node scripts/check-standard.mjs .` và sửa lỗi thuộc phạm vi.
  - Ghi `docs/CHANGELOG.md` và `docs/JOURNAL.md` đúng bảng và giới hạn ghi ở đầu mỗi file (JOURNAL tối đa 40 dòng).
  - Tên file, thư mục, nhánh, dòng đầu commit: tiếng Anh không dấu (`feat/dropdown-token`, `feat(ui): add dropdown tokens`); nội dung docs và giao diện: tiếng Việt.
  - Nhánh làm việc từ `dev`, PR vào `dev`, không tự merge; không đường dẫn tuyệt đối theo máy trong file commit.

## Subagent: coder + reviewer

Repo có subagent tại `.claude/agents/`: **`coder`** và **`reviewer`** — mẫu tại `assets/Template - subagent-coder.md` và `assets/Template - subagent-reviewer.md` của skill `sb-new-repo`. Cách dùng theo `Rules/AI Repo Rules.md` mục "Subagent và CodeGraph": main agent tự làm việc nhỏ/vừa; giao `coder` việc lớn kèm brief tự đủ; gọi `reviewer` trước PR khi đổi logic đáng kể.
