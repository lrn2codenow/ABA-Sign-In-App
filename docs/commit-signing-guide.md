# Verified Commit Signing Guide

Some protected branches in this repository require every commit to carry a
verified cryptographic signature. Follow the steps below to configure commit
signing locally so that your pushes satisfy the protection rule.

## 1. Generate a GPG key

```bash
gpg --full-generate-key
```

When prompted:

1. Select the default **RSA and RSA** key type.
2. Choose a key size of **4096 bits**.
3. Specify a key that **never expires** (or pick an expiration date that suits
your security policy).
4. Provide the real name and email address that match the email you use for
Git commits in this repository.

GPG will prompt for a passphrase; choose a strong one and store it securely.

## 2. List your keys and copy the key ID

```bash
gpg --list-secret-keys --keyid-format=long
```

Locate the `sec` line that includes your email address, for example:

```
sec   rsa4096/`3AA5C34371567BD2` 2024-01-01 [SC]
```

Copy the portion after `rsa4096/`; in the example above the key ID is
`3AA5C34371567BD2`.

## 3. Configure Git to sign commits automatically

Tell Git to use your key for signing and to sign every commit by default:

```bash
git config --global user.signingkey 3AA5C34371567BD2
git config --global commit.gpgsign true
```

If you prefer to sign commits only in this repository, omit the `--global`
flag and run the commands within the project directory.

## 4. Export the public key to GitHub

```bash
gpg --armor --export 3AA5C34371567BD2
```

Copy the full output (including the `-----BEGIN PGP PUBLIC KEY BLOCK-----`
header) and add it as a **GPG key** in your GitHub account:

1. Visit <https://github.com/settings/keys>.
2. Click **New GPG key**.
3. Paste the exported key material and save.

GitHub will now verify signatures that use this key.

## 5. Sign an existing commit (optional)

If you have unpushed commits that were created before signing was enabled, you
can amend them. For the most recent commit:

```bash
git commit --amend --no-edit --gpg-sign
```

For a series of commits that need signing, you can interactively rebase and
reword each commit, signing as you go:

```bash
git rebase --exec 'git commit --amend --no-edit --gpg-sign' -i <base-commit>
```

## 6. Troubleshooting

- **Pinentry errors** – Install a graphical or terminal pinentry program so
  GPG can prompt for your passphrase (`pinentry-tty` works well in terminals).
- **Multiple emails** – Add every email you use for commits as an identity to
  the same GPG key or upload additional keys to GitHub.
- **macOS keychain prompts** – You can cache the passphrase via
  `gpgconf --launch gpg-agent` and configure the agent through
  `~/.gnupg/gpg-agent.conf`.

Once these steps are complete, future commits will include a verified
signature, unblocking merges into protected branches.
