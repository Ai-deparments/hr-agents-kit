import CountUp from "./reactbits/CountUp";

/** KPI number that counts up (react-bits CountUp); non-numeric values ("—", "3 / 10") are shown as they are. */
export function AnimatedValue({ value }: { value: string | number }) {
  const raw = String(value).trim();
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return <>{value}</>;
  const decimals = raw.includes(".") ? raw.split(".")[1].length : 0;
  return <CountUp to={Number(raw)} decimals={decimals} duration={0.9} separator=" " />;
}
