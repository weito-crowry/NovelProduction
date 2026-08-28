import type {
  InputHTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes,
} from "react";

interface FieldLabelProps {
  htmlFor: string;
  children: ReactNode;
}

export function FieldLabel({ htmlFor, children }: FieldLabelProps) {
  return <label htmlFor={htmlFor}>{children}</label>;
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="field-control" {...props} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className="field-control" {...props} />;
}
