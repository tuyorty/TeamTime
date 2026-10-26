import { Compass } from "lucide-react";
import { Link } from "react-router";

import { EmptyState } from "@/components/domain/feedback";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <EmptyState
      icon={Compass}
      title="Такой страницы нет"
      action={
        <Button asChild variant="primary">
          <Link to="/">На главную</Link>
        </Button>
      }
    >
      Возможно, ссылка устарела. Табель недели и отчёты за месяц доступны из меню.
    </EmptyState>
  );
}
