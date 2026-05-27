import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Copy, Scissors, ClipboardPaste, SelectAll, Undo2, Redo2 } from 'lucide-react';

interface ContextMenuItem {
  label: string;
  icon?: React.ReactNode;
  shortcut?: string;
  action: () => void;
  disabled?: boolean;
  divider?: boolean;
}

interface ContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
}

export function ContextMenu({ x, y, items, onClose }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x, y });

  // 确保菜单不超出屏幕
  useEffect(() => {
    if (menuRef.current) {
      const rect = menuRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      let newX = x;
      let newY = y;

      if (x + rect.width > viewportWidth) {
        newX = viewportWidth - rect.width - 8;
      }
      if (y + rect.height > viewportHeight) {
        newY = viewportHeight - rect.height - 8;
      }

      setPosition({ x: Math.max(0, newX), y: Math.max(0, newY) });
    }
  }, [x, y]);

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  return (
    <div
      ref={menuRef}
      className="context-menu"
      style={{
        position: 'fixed',
        left: position.x,
        top: position.y,
        zIndex: 9999,
      }}
    >
      {items.map((item, index) => {
        if (item.divider) {
          return <div key={index} className="context-menu-divider" />;
        }

        return (
          <button
            key={index}
            className={`context-menu-item ${item.disabled ? 'disabled' : ''}`}
            onClick={() => {
              if (!item.disabled) {
                item.action();
                onClose();
              }
            }}
            disabled={item.disabled}
          >
            {item.icon && <span className="context-menu-icon">{item.icon}</span>}
            <span className="context-menu-label">{item.label}</span>
            {item.shortcut && (
              <span className="context-menu-shortcut">{item.shortcut}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// 预设的右键菜单项
export function createEditMenuItems({
  onCut,
  onCopy,
  onPaste,
  onSelectAll,
  onUndo,
  onRedo,
  hasSelection,
  canUndo,
  canRedo,
}: {
  onCut?: () => void;
  onCopy?: () => void;
  onPaste?: () => void;
  onSelectAll?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  hasSelection?: boolean;
  canUndo?: boolean;
  canRedo?: boolean;
}): ContextMenuItem[] {
  const items: ContextMenuItem[] = [];

  if (onUndo) {
    items.push({
      label: '撤销',
      icon: <Undo2 size={14} />,
      shortcut: 'Ctrl+Z',
      action: onUndo,
      disabled: !canUndo,
    });
  }

  if (onRedo) {
    items.push({
      label: '重做',
      icon: <Redo2 size={14} />,
      shortcut: 'Ctrl+Y',
      action: onRedo,
      disabled: !canRedo,
    });
  }

  if (onUndo || onRedo) {
    items.push({ label: '', divider: true, action: () => {} });
  }

  if (onCut) {
    items.push({
      label: '剪切',
      icon: <Scissors size={14} />,
      shortcut: 'Ctrl+X',
      action: onCut,
      disabled: !hasSelection,
    });
  }

  if (onCopy) {
    items.push({
      label: '复制',
      icon: <Copy size={14} />,
      shortcut: 'Ctrl+C',
      action: onCopy,
      disabled: !hasSelection,
    });
  }

  if (onPaste) {
    items.push({
      label: '粘贴',
      icon: <ClipboardPaste size={14} />,
      shortcut: 'Ctrl+V',
      action: onPaste,
    });
  }

  if (onSelectAll) {
    items.push({ label: '', divider: true, action: () => {} });
    items.push({
      label: '全选',
      icon: <SelectAll size={14} />,
      shortcut: 'Ctrl+A',
      action: onSelectAll,
    });
  }

  return items;
}

// Hook: 使用右键菜单
export function useContextMenu() {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [menuItems, setMenuItems] = useState<ContextMenuItem[]>([]);

  const openMenu = useCallback((e: React.MouseEvent, items: ContextMenuItem[]) => {
    e.preventDefault();
    e.stopPropagation();
    setPosition({ x: e.clientX, y: e.clientY });
    setMenuItems(items);
    setIsOpen(true);
  }, []);

  const closeMenu = useCallback(() => {
    setIsOpen(false);
  }, []);

  return {
    isOpen,
    position,
    menuItems,
    openMenu,
    closeMenu,
  };
}
