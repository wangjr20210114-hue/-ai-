import MarkdownRenderer from '../../../../components/common/MarkdownRenderer';
import type { SearchMeta } from '../../model';


export function TextRenderer({
  content,
  searchMeta,
  streaming,
}: {
  content: string;
  searchMeta?: SearchMeta;
  streaming?: boolean;
}) {
  return (
    <MarkdownRenderer
      content={content}
      searchMeta={searchMeta}
      streaming={streaming}
    />
  );
}
