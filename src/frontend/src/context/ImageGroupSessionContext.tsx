import { createContext, useContext, type ReactNode } from "react";

export type ImageGroupSession = {
  groupId: string;
  /** Evidência compartilhada pelo grupo (aba de técnicas). */
  evidenceId: string | null;
  selectionSource: "original" | "derivative";
};

const ImageGroupSessionContext = createContext<ImageGroupSession | null>(null);

export function ImageGroupSessionProvider({
  value,
  children,
}: {
  value: ImageGroupSession;
  children: ReactNode;
}) {
  return <ImageGroupSessionContext.Provider value={value}>{children}</ImageGroupSessionContext.Provider>;
}

export function useImageGroupSession(): ImageGroupSession | null {
  return useContext(ImageGroupSessionContext);
}
