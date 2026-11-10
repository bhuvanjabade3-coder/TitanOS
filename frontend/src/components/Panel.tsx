import { motion } from "framer-motion";
import type { ReactNode } from "react";

export function Panel({
  title,
  aside,
  children,
  className = "",
  index = 0,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  index?: number;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: index * 0.05, ease: [0.2, 0.8, 0.2, 1] }}
      className={`glass p-5 ${className}`}
    >
      <header className="mb-4 flex items-center justify-between">
        <h2 className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">{title}</h2>
        {aside}
      </header>
      {children}
    </motion.section>
  );
}
