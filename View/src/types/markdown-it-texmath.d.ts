declare module 'markdown-it-texmath' {
  import type MarkdownIt from 'markdown-it'
  import type * as Katex from 'katex'

  export interface TexmathOptions {
    engine: typeof Katex
    delimiters?: string | string[]
    outerSpace?: boolean
    katexOptions?: Katex.KatexOptions
  }

  const texmath: (md: MarkdownIt, options?: TexmathOptions) => void
  export default texmath
}
