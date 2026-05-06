import { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

interface QuickActionCardProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  onClick?: () => void;
}

export function QuickActionCard({ icon, title, description, onClick }: QuickActionCardProps) {
  return (
    <Card 
      onClick={onClick}
      className={`cursor-pointer transition-colors hover:bg-muted/50 border-border bg-card`}
    >
      <CardHeader className="flex flex-row items-center justify-between p-6">
        <div className="flex items-center gap-4">
          {icon && <div className="text-muted-foreground">{icon}</div>}
          <div className="flex flex-col space-y-1.5">
            <CardTitle className="text-base">{title}</CardTitle>
            {description && <CardDescription className="text-sm">{description}</CardDescription>}
          </div>
        </div>
        <ChevronRight className="h-5 w-5 text-muted-foreground" />
      </CardHeader>
    </Card>
  );
}


