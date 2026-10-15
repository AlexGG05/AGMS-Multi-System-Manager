const assert=require('node:assert/strict');
const {sshKey,sshData,keysym,rdpChord}=require('../app/static/remote-controls.js');
assert.equal(sshKey('c',{Ctrl:true}),'\x03');assert.equal(sshKey('v',{Ctrl:true}),'\x16');
assert.equal(sshKey('c',{Ctrl:true,Alt:true,Shift:true}),'\x1b\x03');
assert.equal(sshKey('Tab',{Alt:true}),'\x1b\t');assert.equal(sshKey('Tab',{Shift:true}),'\x1b[Z');
assert.equal(sshKey('Enter'),'\r');assert.equal(sshKey('Esc'),'\x1b');
assert.equal(sshKey(' ',{Ctrl:true}),'\x00');assert.equal(sshKey('?',{Ctrl:true}),'\x7f');
assert.equal(sshKey('c',{Shift:true}),'C');assert.equal(sshKey('1',{Shift:true}),'!');
assert.equal(sshData('cat',{Ctrl:true}),'\x03at');assert.equal(sshData('😀a',{Alt:true}),'\x1b😀a');
assert.equal(sshData('\x1b[A',{Ctrl:true}),'\x1b[1;5A');assert.equal(sshData('\x1b[200~paste\x1b[201~',{Ctrl:true}),'\x1b[200~paste\x1b[201~');
for(const [key,end] of [['ArrowUp','A'],['ArrowDown','B'],['ArrowRight','C'],['ArrowLeft','D']]){assert.equal(sshKey(key),'\x1b['+end);assert.equal(sshKey(key,{},true),'\x1bO'+end);assert.equal(sshKey(key,{Ctrl:true,Alt:true,Shift:true}),'\x1b[1;8'+end)}
for(let i=1;i<=12;i++){assert(sshKey('F'+i).startsWith('\x1b'));assert.equal(keysym('F'+i),0xffbd+i)}
assert.equal(sshKey('F1',{Ctrl:true}),'\x1b[1;5P');assert.equal(sshKey('F12',{Alt:true}),'\x1b[24;3~');
assert.deepEqual(rdpChord('c',{Ctrl:true}),[[0xffe3,1],[99,1],[99,0],[0xffe3,0]]);
assert.deepEqual(rdpChord('Delete',{Ctrl:true,Alt:true}),[[0xffe3,1],[0xffe9,1],[0xffff,1],[0xffff,0],[0xffe9,0],[0xffe3,0]]);
assert.deepEqual(rdpChord('Tab',{Alt:true}),[[0xffe9,1],[0xff09,1],[0xff09,0],[0xffe9,0]]);
assert.deepEqual(rdpChord('c',{Shift:true}),[[0xffe1,1],[67,1],[67,0],[0xffe1,0]]);
assert.deepEqual(rdpChord('r',{Super:true}),[[0xffeb,1],[114,1],[114,0],[0xffeb,0]]);
assert.equal(keysym('😀'),0x0101f600);assert.equal(sshKey('unknown'),'');assert.deepEqual(rdpChord('unknown'),[]);
console.log('PASS SSH control bytes, terminal modes, all arrow/function keys, Unicode, modifier combinations and ordered RDP press/release');
