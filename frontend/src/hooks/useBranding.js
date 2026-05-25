import { useContext } from "react";
import { BrandingContext } from "../store/BrandingContext";

export default function useBranding() {
  const context = useContext(BrandingContext);

  if (!context) {
    throw new Error("useBranding must be used within BrandingProvider");
  }

  return context;
}
