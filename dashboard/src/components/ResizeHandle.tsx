interface Props {
  onMouseDown: (e: React.MouseEvent) => void;
}

export function ResizeHandle({ onMouseDown }: Props) {
  return (
    <div
      onMouseDown={onMouseDown}
      className="relative w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-accent/60 active:bg-accent"
    />
  );
}
