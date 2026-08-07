"""
HTTPS for the add-on, using a certificate authority of its own.

Why this exists: browsers only allow offline caching (a service worker) on an
https origin, and a home network has no public name that a real certificate
could be issued for. So the add-on runs a tiny private CA, keeps it in /data so
it survives updates, and issues itself a server certificate. Install the CA once
per phone and https://<pi>:8443 becomes a trusted address - no domain, no port
forwarding, nothing outside the house involved.

The CA key never leaves /data, and it signs exactly one certificate: this
server's. Plain http on 8080 keeps running alongside, because the Nest Hub
can't be given a private CA.
"""

import os
import re
import shutil
import subprocess
import time

CA_YEARS = 10
LEAF_DAYS = 800          # comfortably under the ~825 day ceiling Apple applies
                         # even to certificates from user-added roots
RENEW_WITHIN_DAYS = 30

CA_NAME = "Home Meal Planner Local CA"


class TLSUnavailable(RuntimeError):
    """Raised when a certificate could not be produced. The caller carries on
    serving plain http rather than refusing to start - a kitchen display that
    still works beats a tidy failure."""


def _openssl():
    found = shutil.which("openssl")
    if not found:
        raise TLSUnavailable(
            "The openssl command isn't in this image, so an https certificate "
            "can't be generated. Rebuild the add-on to pick it up.")
    return found


def _run(args):
    proc = subprocess.run([_openssl()] + args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TLSUnavailable("openssl %s failed: %s"
                             % (args[0], (proc.stderr or "").strip()[:400]))
    return proc.stdout


_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def san_list(hosts):
    """Turn names and addresses into an openssl subjectAltName value.

    Modern browsers ignore the certificate's common name entirely and look only
    at this list, so every address the app might be reached on has to appear.
    Order is preserved and duplicates dropped, which keeps the string stable -
    it is compared against the last one used to decide whether to reissue."""
    seen, parts = set(), []
    for host in hosts:
        host = (host or "").strip()
        if not host or host in seen:
            continue
        seen.add(host)
        parts.append(("IP:" if _IPV4.match(host) else "DNS:") + host)
    if not parts:
        raise TLSUnavailable("No hostnames or addresses to put in the certificate.")
    return ",".join(parts)


def _days_left(cert):
    """Days until the certificate expires, or -1 if it can't be read."""
    try:
        out = _run(["x509", "-in", cert, "-noout", "-enddate"])
        stamp = out.split("=", 1)[1].strip()
    except Exception:
        return -1
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S %Y GMT"):
        try:
            return int((time.mktime(time.strptime(stamp, fmt)) - time.time()) / 86400)
        except ValueError:
            continue
    return -1


def _make_ca(ca_crt, ca_key):
    _run(["ecparam", "-genkey", "-name", "prime256v1", "-out", ca_key])
    os.chmod(ca_key, 0o600)
    _run(["req", "-new", "-x509", "-key", ca_key, "-out", ca_crt,
          "-days", str(CA_YEARS * 365),
          "-subj", "/CN=%s/O=Home Meal Planner" % CA_NAME,
          # iOS refuses to trust a root that has no basicConstraints extension.
          "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
          "-addext", "keyUsage=critical,keyCertSign,cRLSign",
          "-addext", "subjectKeyIdentifier=hash"])


def _make_leaf(ca_crt, ca_key, crt, key, sans, workdir):
    csr = os.path.join(workdir, "server.csr")
    ext = os.path.join(workdir, "server.ext")
    _run(["ecparam", "-genkey", "-name", "prime256v1", "-out", key])
    os.chmod(key, 0o600)
    _run(["req", "-new", "-key", key, "-out", csr, "-subj", "/CN=Home Meal Planner"])
    with open(ext, "w") as fh:
        fh.write("basicConstraints=critical,CA:FALSE\n"
                 "keyUsage=critical,digitalSignature,keyEncipherment\n"
                 "extendedKeyUsage=serverAuth\n"
                 "subjectAltName=%s\n"
                 "subjectKeyIdentifier=hash\n"
                 "authorityKeyIdentifier=keyid,issuer\n" % sans)
    _run(["x509", "-req", "-in", csr, "-CA", ca_crt, "-CAkey", ca_key,
          "-CAcreateserial", "-out", crt, "-days", str(LEAF_DAYS),
          "-extfile", ext])
    for path in (csr, ext):
        try:
            os.remove(path)
        except OSError:
            pass


def ensure(cert_dir, hosts):
    """Make sure a usable certificate exists; return (crt, key, ca_crt).

    The CA is created once and then left alone: regenerating it would silently
    break the trust every phone in the house has already been given, with no
    symptom beyond "the app stopped loading". The server certificate is reissued
    when the list of names changes (the Pi moved to a new address) or when it is
    within a month of expiring."""
    os.makedirs(cert_dir, exist_ok=True)
    ca_crt = os.path.join(cert_dir, "ca.crt")
    ca_key = os.path.join(cert_dir, "ca.key")
    crt = os.path.join(cert_dir, "server.crt")
    key = os.path.join(cert_dir, "server.key")
    stamp = os.path.join(cert_dir, "server.sans")

    sans = san_list(hosts)

    if not (os.path.isfile(ca_crt) and os.path.isfile(ca_key)):
        _make_ca(ca_crt, ca_key)

    previous = ""
    if os.path.isfile(stamp):
        with open(stamp) as fh:
            previous = fh.read().strip()

    if (not os.path.isfile(crt) or not os.path.isfile(key)
            or previous != sans
            or _days_left(crt) < RENEW_WITHIN_DAYS):
        _make_leaf(ca_crt, ca_key, crt, key, sans, cert_dir)
        with open(stamp, "w") as fh:
            fh.write(sans)

    return crt, key, ca_crt


def fingerprint(ca_crt):
    """Short SHA-256 fingerprint, shown on the setup page so the certificate
    being installed can be checked against the one the server actually has."""
    try:
        out = _run(["x509", "-in", ca_crt, "-noout", "-fingerprint", "-sha256"])
        return out.split("=", 1)[1].strip()
    except Exception:
        return ""
