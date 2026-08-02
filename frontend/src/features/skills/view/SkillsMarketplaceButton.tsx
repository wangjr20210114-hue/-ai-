import { Button } from 'tdesign-react';
import { AppIcon } from 'tdesign-icons-react';
import { createPortal } from 'react-dom';

import { useSkillMarketplaceController } from '../controller/useSkillMarketplaceController';
import { SkillsMarketplaceShell } from './SkillsMarketplaceShell';

export default function SkillsMarketplaceButton() {
  const controller = useSkillMarketplaceController();

  return <>
    <Button
      data-onboarding="skills"
      className="sidebar-settings-button"
      block
      variant="text"
      icon={<AppIcon />}
      loading={controller.loading && !controller.visible}
      onClick={() => void controller.openMarketplace()}
    >{controller.t('skillsMarketplace')}</Button>
    {controller.visible && typeof document !== 'undefined' && createPortal(
      <SkillsMarketplaceShell controller={controller} />,
      document.body,
    )}
  </>;
}
