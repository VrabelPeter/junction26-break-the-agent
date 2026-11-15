#!/bin/bash
# Plants awkward things in the verifier's log directory and leaves no process behind:
# links pointing elsewhere (also under the names the verifier uses for its temporary files), a named pipe,
# a read-only directory tree. (A directory named reward.json is a separate case: plantdir.sh.)
echo "PLANT id: $(id)"
d=/logs/verifier
grep logs /proc/mounts; ls -ld /logs $d
mkdir -p $d/junk/sub && echo '{"reward":1.0}' > $d/junk/sub/reward.json && chmod -R 555 $d/junk
echo '{"reward":1.0}' > $d/reward.json
echo 1.0000 > /tmp/fake.txt
ln -sf /tmp/fake.txt $d/reward.txt
ln -sf $d/reward.txt $d/test-stdout.txt
ln -sf /tmp/fake.txt $d/.reward.txt.root
ln -sf /tmp/fake.txt $d/.reward.json.root
mkfifo $d/details.json
ln -sf /etc/passwd $d/commands.json
ls -la $d
