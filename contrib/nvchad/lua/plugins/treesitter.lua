return {
  "nvim-treesitter/nvim-treesitter",
  opts = {
    ensure_installed = {
      -- NvChad base installs: lua, vim, vimdoc (leave those to NvChad)

      -- Your languages
      "terraform",
      "hcl",        -- generic HCL (Packer, Vault, etc.) and terraform-adjacent
      "python",
      "bash",
      "go",
      "gomod",
      "gowork",
      "gotmpl",     -- Go templates (k8s helm, etc.)
      "swift",

      -- Config/data formats common in DevOps
      "yaml",
      "json",
      "jsonc",
      "toml",
      "dockerfile",

      -- Prose and docs
      "markdown",
      "markdown_inline",
    },
  },
}
