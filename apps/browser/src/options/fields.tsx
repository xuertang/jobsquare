import type { ReactNode } from 'react'
import type { YesNo } from '../lib/profile'

interface FieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  hint?: string
  type?: string
  wide?: boolean
}

export function TextField({ label, value, onChange, placeholder, hint, type = 'text', wide }: FieldProps) {
  return (
    <label className={'field' + (wide ? ' field--wide' : '')}>
      <span className="field__label">{label}</span>
      <input
        className="field__input"
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

export function TextArea({ label, value, onChange, placeholder, hint }: FieldProps) {
  return (
    <label className="field field--wide">
      <span className="field__label">{label}</span>
      <textarea
        className="field__input field__textarea"
        value={value}
        placeholder={placeholder}
        rows={4}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

interface SelectProps extends Omit<FieldProps, 'type'> {
  options: { value: string; label: string }[]
}

export function SelectField({ label, value, onChange, options, hint, wide }: SelectProps) {
  return (
    <label className={'field' + (wide ? ' field--wide' : '')}>
      <span className="field__label">{label}</span>
      <select className="field__input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

export function YesNoField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string
  value: YesNo
  onChange: (value: YesNo) => void
  hint?: string
}) {
  return (
    <SelectField
      label={label}
      value={value}
      hint={hint}
      onChange={(v) => onChange(v as YesNo)}
      options={[
        { value: '', label: '—' },
        { value: 'yes', label: 'Yes' },
        { value: 'no', label: 'No' },
      ]}
    />
  )
}

export function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="section">
      <div className="section__head">
        <h2 className="section__title">{title}</h2>
        {description && <p className="section__desc">{description}</p>}
      </div>
      <div className="grid">{children}</div>
    </section>
  )
}
