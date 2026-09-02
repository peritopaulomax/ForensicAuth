import AckDisclaimerModal from "@/components/AckDisclaimerModal";
import { IMDL_DISCLAIMER_BODY, IMDL_DISCLAIMER_TITLE } from "@/lib/imdlDisclaimerAck";

interface Props {
  open: boolean;
  onConfirm: () => void;
}

export default function ImdlDisclaimerModal({ open, onConfirm }: Props) {
  return (
    <AckDisclaimerModal
      open={open}
      title={IMDL_DISCLAIMER_TITLE}
      body={IMDL_DISCLAIMER_BODY}
      onConfirm={onConfirm}
      titleId="imdl-disclaimer-title"
      testId="imdl-disclaimer-modal"
      confirmTestId="imdl-disclaimer-ok"
    />
  );
}
