import { Button } from 'tdesign-react';
import { CheckCircleIcon, RefreshIcon, SearchIcon } from 'tdesign-icons-react';

import type { TranslationKey } from '../../../i18n';
import { groupMarketplaceSkills } from '../model';
import type { SkillMarketplaceController } from './SkillsMarketplaceShell';
import { SkillCatalogCard } from './SkillCatalogCard';

const CATEGORY_LABELS: Record<string, TranslationKey> = {
  foundation: 'skillCategoryFoundation',
  knowledge: 'skillCategoryKnowledge',
  creative: 'skillCategoryCreative',
  productivity: 'skillCategoryProductivity',
  location: 'skillCategoryLocation',
  other: 'skillCategoryOther',
};

const CATEGORY_HINTS: Record<string, TranslationKey> = {
  foundation: 'skillCategoryFoundationHint',
  knowledge: 'skillCategoryKnowledgeHint',
  creative: 'skillCategoryCreativeHint',
  productivity: 'skillCategoryProductivityHint',
  location: 'skillCategoryLocationHint',
  other: 'skillCategoryOtherHint',
};

export function SkillCatalogView({
  controller,
}: {
  controller: SkillMarketplaceController;
}) {
  const {
    catalog, enabledCount, loading, query, refresh, setQuery, t, view,
    visibleSkills,
  } = controller;
  const groupedSkills = groupMarketplaceSkills(visibleSkills);

  return <>
    <section className="skills-page-hero">
      <div>
        <span className="skills-page-eyebrow">{t('skillsEyebrow')}</span>
        <h1>{view === 'enabled' ? t('enabledSkills') : t('composeSkills')}</h1>
        <p>{t('standardSkillsDescription')}</p>
      </div>
      <div className="skills-page-stat"><CheckCircleIcon />{
        loading && catalog.length === 0
          ? t('loading')
          : t('enabledCount', { enabled: enabledCount, total: catalog.length })
      }</div>
    </section>
    <div className="skills-page-toolbar">
      <label>
        <SearchIcon aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('searchSkills')}
        />
      </label>
      <Button
        variant="outline"
        icon={<RefreshIcon />}
        loading={loading}
        onClick={() => void refresh()}
      >{t('refreshStatus')}</Button>
    </div>
    <div className="skills-category-list">
      {groupedSkills.map(([category, skills], groupIndex) => {
        const labelKey = CATEGORY_LABELS[category] || CATEGORY_LABELS.other;
        const hintKey = CATEGORY_HINTS[category] || CATEGORY_HINTS.other;
        return <section className="skills-category" key={category}>
          <header>
            <div><h2>{t(labelKey)}</h2><p>{t(hintKey)}</p></div>
            <span>{skills.length}</span>
          </header>
          <div className="skills-page-grid">
            {skills.map((skill, index) => <SkillCatalogCard
              controller={controller}
              index={groupIndex * 10 + index}
              key={skill.id}
              skill={skill}
            />)}
          </div>
        </section>;
      })}
    </div>
  </>;
}
