import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMessage } from "@/api/queries";
import type { Message } from "@/api/types";
import { dateTime } from "@/lib/format";
import { SourceMessage } from "./SourceMessage";

vi.mock("@/api/queries", () => ({ useMessage: vi.fn() }));

const message: Message = {
  id: 10, chat_id: -12345, message_id: 77, thread_id: 1,
  author_name: "Вымышленный сотрудник", author_tg_id: 100,
  sent_at: "2026-11-08T10:00:00+05:00", source: "telegram", telegram_link: null,
  versions: [
    { id: 102, version: 2, text: "Новые задачи после правки", edited_at: "2026-11-10T09:00:00+05:00", received_at: "2026-11-10T09:01:00+05:00" },
    { id: 101, version: 1, text: "Первоначальный список задач", edited_at: null, received_at: "2026-11-08T10:01:00+05:00" },
  ],
  parses: [
    { id: 201, message_version_id: 101, version: 1, parser_version: 4, kind: "schedule", status: "ok", resolution: "accepted", issues: [], data: null, employee: null, employee_unresolved: false, created_at: "2026-11-12T12:00:00+05:00", is_latest: false },
    { id: 202, message_version_id: 102, version: 2, parser_version: 4, kind: "schedule", status: "partial", resolution: "pending", issues: [], data: null, employee: null, employee_unresolved: false, created_at: "2026-11-12T12:05:00+05:00", is_latest: true },
  ],
};

beforeEach(() => {
  vi.mocked(useMessage).mockReturnValue({ data: message, isLoading: false, error: null, refetch: vi.fn() } as unknown as ReturnType<typeof useMessage>);
});

describe("источник конкретной версии расписания", () => {
  it("показывает выбранный текст и его решение, а не последнюю правку", () => {
    render(<SourceMessage rawId={10} messageVersionId={101} title="Источник" />);
    expect(screen.getByText("Первоначальный список задач")).toBeVisible();
    expect(screen.queryByText("Новые задачи после правки")).not.toBeInTheDocument();
    expect(screen.getByText("принято администратором")).toBeVisible();
    expect(screen.queryByText("ждёт решения")).not.toBeInTheDocument();
    expect(screen.getByText(`Отправлено: ${dateTime(message.sent_at)}`)).toBeVisible();
    expect(screen.getByText(`Разобрано: ${dateTime(message.parses[0]!.created_at)}`)).toBeVisible();
  });

  it("не подменяет недоступную исходную версию последним сообщением", () => {
    render(<SourceMessage rawId={10} messageVersionId={999} title="Источник" />);
    expect(screen.getByText("Исходная версия сообщения недоступна.")).toBeVisible();
    expect(screen.queryByText("Новые задачи после правки")).not.toBeInTheDocument();
  });

  it("без закрепления открывает последнюю правку и позволяет посмотреть исходное сообщение", () => {
    render(<SourceMessage rawId={10} title="Источник" />);
    expect(screen.getByText("Новые задачи после правки")).toBeVisible();
    expect(screen.getByText(`Изменено: ${dateTime(message.versions[0]!.edited_at!)}`)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "исходное" }));
    expect(screen.getByText("Первоначальный список задач")).toBeVisible();
    expect(screen.queryByText("Новые задачи после правки")).not.toBeInTheDocument();
  });
});
