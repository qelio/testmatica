import { Card, Logo } from "@/components/ui";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex flex-1 flex-col items-center px-4 py-10 sm:py-16">
      <Logo className="mb-8" />
      <Card className="w-full max-w-md">{children}</Card>
    </div>
  );
}
