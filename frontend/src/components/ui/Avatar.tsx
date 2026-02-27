import clsx from 'clsx';

interface AvatarProps {
  name: string;
  url?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeMap = {
  sm: 'w-5 h-5 text-[9px]',
  md: 'w-7 h-7 text-xs',
  lg: 'w-9 h-9 text-sm',
};

const bgColors = [
  'bg-indigo-500/30',
  'bg-emerald-500/30',
  'bg-amber-500/30',
  'bg-pink-500/30',
  'bg-cyan-500/30',
  'bg-violet-500/30',
];

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

function hashBg(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash << 5) - hash + name.charCodeAt(i);
  }
  return bgColors[Math.abs(hash) % bgColors.length];
}

export function Avatar({ name, url, size = 'md', className }: AvatarProps) {
  if (url) {
    return (
      <img
        src={url}
        alt={name}
        className={clsx('rounded-full object-cover', sizeMap[size], className)}
      />
    );
  }

  return (
    <div
      className={clsx(
        'rounded-full flex items-center justify-center font-medium text-text-primary',
        sizeMap[size],
        hashBg(name),
        className,
      )}
      title={name}
    >
      {getInitials(name)}
    </div>
  );
}
