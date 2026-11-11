#pragma once

// Syntax-only declarations, not a renderer or SDK ABI substitute.
using GLuint=unsigned;
using GLint=int;
using GLenum=unsigned;
using GLfloat=float;
enum {
    GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_NEAREST, GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE, GL_RGBA, GL_UNSIGNED_BYTE, GL_QUADS, GL_BACK, GL_VERSION,
    GL_VIEWPORT, GL_TRUE, GL_FALSE, GL_DEPTH_TEST, GL_BLEND, GL_COLOR_BUFFER_BIT, GL_PROJECTION,
    GL_MODELVIEW, GL_ONE, GL_ONE_MINUS_SRC_ALPHA, GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE,
    GL_TRIANGLES, GL_NO_ERROR, VGL_MEM_RAM, VGL_MEM_VRAM, SCE_GXM_MULTISAMPLE_NONE,
    GL_FRAMEBUFFER_BINDING, GL_READ_FRAMEBUFFER_BINDING, GL_SCISSOR_BOX, GL_MATRIX_MODE,
    GL_TEXTURE_BINDING_2D, GL_BLEND_SRC_RGB, GL_BLEND_DST_RGB, GL_BLEND_SRC_ALPHA, GL_BLEND_DST_ALPHA,
    GL_BLEND_EQUATION_RGB, GL_BLEND_EQUATION_ALPHA, GL_CURRENT_COLOR, GL_SCISSOR_TEST, GL_CULL_FACE,
    GL_DRAW_FRAMEBUFFER, GL_READ_FRAMEBUFFER, GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_COMPLETE,
    GL_FUNC_ADD, GL_ZERO, GL_DST_ALPHA, GL_PROJECTION_MATRIX, GL_MODELVIEW_MATRIX,
    GL_RGB, GL_COLOR_CLEAR_VALUE, GL_PACK_ALIGNMENT, GL_INVALID_ENUM,
    GL_STACK_OVERFLOW=0x0503, GL_STACK_UNDERFLOW=0x0504
};
extern "C" {
unsigned glGetError();
void glBindTexture(unsigned,GLuint);
void glTexParameteri(unsigned,unsigned,int);
void glTexImage2D(unsigned,int,int,int,int,int,unsigned,unsigned,const void*);
void glBegin(unsigned);
void glVertex2f(float,float);
void glEnd();
void glTexCoord2f(float,float);
void glColor4ub(unsigned char,unsigned char,unsigned char,unsigned char);
void glDisable(unsigned);
void glEnable(unsigned);
void glColor3f(float,float,float);
void glColor4f(float,float,float,float);
void glReadBuffer(unsigned);
void glFinish();
void glReadPixels(int,int,int,int,unsigned,unsigned,void*);
int vglInitExtended(unsigned,int,int,unsigned,unsigned);
const unsigned char* glGetString(unsigned);
unsigned vglMemTotal(unsigned);
void glGetIntegerv(unsigned,GLint*);
void vglWaitVblankStart(int);
void glGenTextures(int,GLuint*);
void glViewport(int,int,int,int);
void glClearColor(float,float,float,float);
void glClear(unsigned);
void glMatrixMode(unsigned);
void glLoadIdentity();
void glLoadMatrixf(const float*);
void glOrtho(double,double,double,double,double,double);
void glTranslatef(float,float,float);
void glBlendFunc(unsigned,unsigned);
void glTexEnvi(unsigned,unsigned,int);
void vglSwapBuffers(int);
void glDeleteTextures(int,const GLuint*);
void glGetFloatv(unsigned,float*);
bool glIsEnabled(unsigned);
void glPushMatrix();
void glPopMatrix();
void glScissor(int,int,int,int);
void glBlendFuncSeparate(unsigned,unsigned,unsigned,unsigned);
void glBlendEquation(unsigned);
void glBlendEquationSeparate(unsigned,unsigned);
void glGenFramebuffers(int,GLuint*);
void glBindFramebuffer(unsigned,GLuint);
void glFramebufferTexture2D(unsigned,unsigned,unsigned,GLuint,int);
unsigned glCheckFramebufferStatus(unsigned);
void glDeleteFramebuffers(int,const GLuint*);
}
