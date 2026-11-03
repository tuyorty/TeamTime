import { Select } from "@/components/ui/field";
import { DEPARTMENTS, type DepartmentFilter as Filter } from "@/lib/departments";

export function DepartmentFilter({ value, onChange }: { value: Filter; onChange: (value: Filter) => void }) {
  return <Select aria-label="Отдел" className="w-auto" value={value} onChange={(event) => onChange(event.target.value as Filter)}>
    <option value="all">Все отделы</option>
    {Object.entries(DEPARTMENTS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
  </Select>;
}
