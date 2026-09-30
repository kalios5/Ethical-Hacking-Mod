# Vulnerable Box Walkthrough
## SaaS E-Commerce Platform — Ethical Hacking Practice Box

---

## Scenario

This box simulates a Software-as-a-Service (SaaS) e-commerce platform — the kind of infrastructure that powers hosted online stores like those offered by Shopify or Odoo. The platform hosts online businesses on shared infrastructure, giving each business their own storefront while keeping the underlying servers, databases, and container runtime common to all tenants.

In this lab, one active tenant store is deployed — a flower shop. The store runs across three Docker containers: an nginx web server handling incoming requests, a Python Flask backend running the application logic, and a PostgreSQL database storing the store's data. All three containers run on a single AWS EC2 Ubuntu instance. The EC2 host has port 80 open for the web storefront and port 22 open for SSH — the latter is used by the platform administrator for legitimate management access, and will later serve as the proof that the attacker has fully compromised the host.

The goal of this box is to walk through a realistic multi-stage attack against a modern web platform, covering eight of the OWASP Top 10 vulnerability categories across a coherent chain where each stage unlocks the next. There are two independent objectives once the admin console is reached — escaping the container to gain root access on the host, and extracting and decrypting sensitive payment data from the database.

---

## Stage 1 — Getting a Foothold: User Registration

The attacker begins as an anonymous guest browsing the storefront. The store is publicly accessible — guests can browse the product catalog, view individual items, and read product descriptions without any account.

The first step requires no vulnerability at all. The platform offers open user registration, as any real e-commerce site would — customers need to be able to create accounts to place orders. The attacker registers a legitimate account through the standard registration form, providing a username, email address, and password of their choosing.

Once registered and logged in, the attacker has a valid authenticated session as a standard customer. This is the starting position for the real attack chain.

---

## Stage 2 — Escalating to Admin: CVE-2026-27641 and Server-Side Template Injection

With a valid user session, the attacker's next goal is to reach the admin console. This requires planting a malicious payload that executes with the application's own privileges and writes a new admin account into the database.

The attack exploits two weaknesses in combination — a path traversal vulnerability in the profile picture upload feature, and a Server-Side Template Injection flaw in Flask's Jinja2 template engine.

### The Upload Vulnerability

The platform allows users to upload a profile picture from their account page. This feature is intentionally restricted to logged-in users — a guest cannot reach it. The upload handler validates the incoming file by checking only the Content-Type header sent by the browser. Content-Type is entirely controlled by whoever sends the request, meaning the attacker can send any file they want and simply label it as an image by setting Content-Type to image/png.

The second flaw is that the filename sent in the upload request is used directly as the save path without sanitisation. In Python, os.path.join will happily resolve path traversal sequences like ../../ — meaning a filename of ../../templates/storefront/cart.html does not save the file inside the intended uploads directory, but instead resolves to the cart template in Flask's templates folder. The cart.html template is chosen deliberately as the target — it is a single page that the attacker can trigger by visiting the cart, and overwriting it does not break the rest of the site, keeping the login, product catalog, and admin console functional throughout the rest of the attack.

The delete_avatar function runs before each save, removing whatever file is currently stored as the user's previous avatar. This means the prior cart.html is deleted before the payload is written in its place, and no file conflict occurs — the payload lands cleanly without a _1 suffix being appended.

### The Payload

The attacker's payload is a plain text file containing Jinja2 template syntax. When Flask renders the cart page, the Jinja2 engine reads cart.html and executes any template blocks it finds. The payload uses the user object that is passed into every template to chain through to the SQLAlchemy database session — the same session the application itself uses for all database writes:

```
user.__class__                 the User database model
user.__class__.query           SQLAlchemy's query interface for that model
user.__class__.query.session   the active database session
```

Through this chain the payload creates a new User object, sets its role to admin, and commits it to the database — all from inside the template engine, without ever having access to the operating system or any external resources. The payload also includes an existence check so it only fires once even if the cart page is visited multiple times after the overwrite.

Importantly, the template context is hardened so the attacker cannot reach more dangerous capabilities. The real Flask config object has been replaced with a stripped proxy that exposes only non-sensitive values, and __builtins__ has been removed from the template environment. The standard SSTI chain that would normally reach os.popen() through config.__class__.__init__.__globals__ reaches a dead end — the proxy's globals contain nothing useful. The payload can write a database row. It cannot launch processes, read files, or interact with the system in any other way. This keeps the admin console as a genuine required gate — the only way forward is to log in as the newly created admin user.

### The Result

After uploading the payload and visiting the cart page, the database now contains a new user with the admin role. The attacker logs in as that user and the admin console is accessible for the first time.

---

## Stage 3A — Extracting Data: Database Console and Decryption

The admin console includes a database console intended for debugging and daily operations. This is a legitimate feature of the platform — operators need visibility into the data their stores generate. The attacker uses it to directly query and dump the payment and customer PII tables.

The data in these tables is not stored in plaintext. Payment details and customer records are encrypted with AES before being written to the database. At first glance this looks like a meaningful protection — even with database access, the attacker sees only ciphertext.

However the encryption key is hardcoded in the backend application's config file rather than being stored in a secure secrets manager or injected from the environment at runtime. A hardcoded key is effectively the same as no encryption at all — anyone with access to the source code or the application's configuration can recover it. The attacker reads the key from the config and decrypts the full dataset.

An additional bonus is present for attackers who look closely: one particularly sensitive column in the database uses AES in ECB mode rather than CBC or GCM. ECB encrypts each 16-byte block independently, which means identical blocks of plaintext always produce identical blocks of ciphertext. This leaks structural patterns in the data — for instance, identical card number prefixes produce visibly identical ciphertext blocks — meaning the data can be partially analysed even without the key, just by observing the patterns.

---

## Stage 3B — Escaping the Container: Malicious Plugin and CopyEscape

The second post-admin objective is escaping from the tenant container onto the underlying host. This is the more technically involved path and the one that demonstrates the real-world risk of a poorly isolated multi-tenant platform.

### The Plugin System

The admin console includes a plugin manager that allows tenant operators to upload custom integration modules — extensions for things like alternative sign-in methods, two-factor authentication adapters, or shipping and payment connectors. This is a real feature class that platforms like Odoo offer: bring-your-own-code integrations that the platform executes on the tenant's behalf.

The platform runs uploaded plugin code as root inside the container. It does not verify the plugin's authenticity, does not check a signature, and does not sandbox the execution environment. The attacker uploads a plugin that appears to initialise a 2FA module — it returns the string "2FA module initialized successfully" — but its actual behaviour is to arm the CopyEscape trap.

### What the Plugin Does

When the platform executes the plugin, it:

Verifies that two required binary files are present in the plugin directory — the `minimal-monitor` binary and `libwatchedfile.so`. Sets the monitor binary executable. Writes a cron entry to `/etc/cron.d/platform_monitor` with the correct shell environment headers and 0644 permissions. The cron entry launches `minimal-monitor` with `LD_PRELOAD` set to `libwatchedfile.so` and with the working directory set to the plugin folder so the monitor can find its configuration file `payload_scripts.txt` at runtime.

Within one minute, the container's cron daemon picks up the entry and launches the monitor in the background.

### The Monitor and the Trap

The minimal-monitor binary reads its configuration from `payload_scripts.txt` — a plain text key-value file that controls all of its paths and targets without requiring recompilation. When it starts it calls setup_layout(), which first clears away any legitimate files that might be in the way — if the application has already written a regular file at `/logs/app.log`, the monitor removes it. It then builds the exploit layout:

It creates `/logs/app.log/` as a directory. This is the key trick — a directory named to look like a log file. Docker's copy command sees the path `/logs/app.log` and begins descending into it to read its contents, not realising it has entered a directory rather than copying a file. Inside this disguised directory the monitor creates a 16 megabyte file called `aaa.txt`. The size is deliberate — docker cp needs long enough reading this file for the race condition to be won. It creates an `escape/` subdirectory as the pivot target. It creates a symlink called `.swap-escape` that points at `/root/.ssh/` on the HOST filesystem — not inside the container.

The monitor then enters a watch loop using inotify, listening for filesystem access events on the disguised `/logs/app.log/` directory.

### The Race Condition

On the host, a cron job runs every two minutes as root. It calls `docker cp` to pull the log file from the container to a central collection directory on the host — a routine log management task. This is the trigger.

When `docker cp` begins reading `aaa.txt` inside the container, inotify fires an access event. The monitor immediately performs two rename operations:

First, it moves `escape/` to `.old-escape/` — getting the real directory out of the way. Then it moves `.swap-escape` (the symlink) into the position where `escape/` used to be, giving it the name `escape`.

Docker cp is still in the middle of reading the directory. It now descends into what it thinks is the `escape/` subdirectory — but that path is now the symlink pointing at `/root/.ssh/` on the host. Docker's archive extraction code follows the symlink and writes the collected files into the host's `/root/.ssh/` directory.

The monitor's payload — the contents of the `authorized_keys` file it created inside the container — is written to `/root/.ssh/authorized_keys` on the host. This file contains the attacker's SSH public key.

### Why the SSH Key

Planting the SSH public key is chosen as the demonstration payload because it has an immediately verifiable and unambiguous outcome — the attacker can SSH into the EC2 host on port 22 and receive a root shell, proving beyond any doubt that they have root-level write access to the host filesystem. The key itself is not the point; the point is that the attacker can now write any file anywhere on the host as root. They could plant any backdoor, modify any system binary, or read any file on the machine. The SSH key is simply the most legible proof of that capability.

---

## What This Demonstrates

The attack chain as a whole illustrates several interconnected real-world lessons. Content-Type is not image validation — the upload check looked reasonable but was checking the wrong thing. Path sanitisation must cover every parameter that influences a file write — `secure_filename` was not applied to the save path. Template injection gives an attacker the application's own database access — the payload needed no external capabilities because the application's own ORM was within reach. Hardcoded encryption keys nullify encryption at rest — the database was encrypted but the key was right next to the data. Third-party code execution without integrity checks is inherently dangerous — the platform trusted an uploaded plugin with root privileges and no verification. A routine operational task — log collection — became the exploit trigger through an unpatched container runtime.

Each of these findings corresponds to a distinct OWASP Top 10 category, and together they model the kind of layered, realistic attack chain that a penetration tester or red team would construct against a real SaaS platform.
