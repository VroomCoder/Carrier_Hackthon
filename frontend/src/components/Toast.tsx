import type { Toast } from "../types";

interface ToastContainerProps {
  toasts: Toast[];
  onRemove: (id: string) => void;
}

const borderColors: Record<string, string> = {
  success: "border-brand-400",
  error: "border-red-500",
  warning: "border-amber-400",
  info: "border-blue-400",
};

export default function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`toast-enter bg-white border-l-4 ${borderColors[toast.type]} rounded-lg shadow-sm px-4 py-3 min-w-[280px] max-w-sm flex items-start justify-between gap-3`}
        >
          <p className="text-sm text-gray-700">{toast.message}</p>
          <button
            onClick={() => onRemove(toast.id)}
            className="text-gray-400 hover:text-gray-600 text-lg leading-none"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
